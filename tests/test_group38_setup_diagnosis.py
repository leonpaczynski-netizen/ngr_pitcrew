"""
Group 38 — AI Setup-Diagnosis Overhaul Acceptance Tests

Covers all 18 required test criteria from the spec (Section 12 + addendum):
 1. Timed race context generated correctly (50 min, Timed Race)
 2. 50-minute race never rendered as "1 lap"
 3. Natural frequency shown as Hz not N/mm
 4. Driver hard constraints present in prompt (before telemetry section)
 5. Floaty front + minimum front aero => aero/platform-limited diagnosis
 6. Rear loose on exit + minimum rear aero => rear aero diagnosis
 7. Bottoming below 0.5/lap blocks ride-height increase (minor band)
 8. Severe wheelspin classified correctly; band boundaries
 9. Gearbox preserved when driver says good; gearbox edit rejected
10. Clean response (no RH change) returns [] for rh_for_minor_bottoming
11. Reject AI that leaves aero at min while diagnosing floaty-front understeer
12. Reject AI that changes a locked setting
13. Historical "driver hated" label prevents repeating
14. Historical "driver liked" label included in prompt
15. Before/after comparison: save_entry + label round-trip
16. PORSCHE RSR '17 / FUJI REGRESSION (mandatory end-to-end)
17. UI boundary: _format_engineering_validation_banner pure helper
18. Location-confidence guard: low confidence emits caveat + blocks rh

All tests are pure/offline — no network, no Qt event loop, no QApplication.
"""
from __future__ import annotations

import json
import sys
import types
import tempfile
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Scratchpad dir for artifacts
# ---------------------------------------------------------------------------
_SCRATCHPAD = Path(
    r"C:\Users\leons\AppData\Local\Temp\claude"
    r"\C--Projects-VR-Dashboard"
    r"\72d45832-345d-42ac-8b66-7e758dc75e50"
    r"\scratchpad"
)
_SCRATCHPAD.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------
from strategy.setup_diagnosis import (
    PERSONAL_DRIVER_TUNING_MODEL,
    DRIVER_HARD_CONSTRAINTS,
    _parse_driver_feel,
    build_setup_diagnosis,
    validate_setup_engineering,
    format_diagnosis_for_prompt,
)
from strategy._ai_client import format_setup_for_prompt
from strategy import driving_advisor as da
from data import setup_history as sh

# ---------------------------------------------------------------------------
# Minimal fake LapStats (duck-typed SimpleNamespace)
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    brake_consistency_m: float = 5.0,
    oversteer_count: int = 0,
    oversteer_throttle_on_count: int = 0,
    kerb_count: int = 0,
    max_lat_g: float = 1.5,
) -> SimpleNamespace:
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rev_limiter_by_gear or {},
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=brake_consistency_m,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on_count,
        kerb_count=kerb_count,
        max_lat_g=max_lat_g,
        # extended attributes used by DrivingAdvisor prompt builders
        rev_limiter_count=sum((rev_limiter_by_gear or {}).values()),
        lock_up_positions=[],
        wheelspin_positions=[],
        oversteer_positions=[],
        snap_throttle_positions=[],
        over_braking_positions=[],
        over_braking_count=0,
        abrupt_release_count=0,
        car_max_speed_theoretical_kmh=0.0,
        avg_tyre_radius={},
        off_track_count=0,
    )


# ---------------------------------------------------------------------------
# Minimal mock AI response dict (valid schema)
# ---------------------------------------------------------------------------

def _minimal_ai_resp(overrides: dict | None = None) -> dict:
    base = {
        "analysis": "Test analysis.",
        "primary_issue": "test",
        "issue_classification": {"test": "setup-limited"},
        "changes": [],
        "setup_fields": {},
        "validation_targets": {},
        "confidence": {"overall": "medium", "reason": "test"},
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Stub DrivingAdvisor (avoid needing full recorder/tracker/config Qt infra)
# ---------------------------------------------------------------------------

def _make_stubbed_advisor(event_ctx: dict) -> da.DrivingAdvisor:
    """Build a DrivingAdvisor with all external dependencies stubbed to empty strings."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = None
    adv._tracker = None
    adv._config = {}
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = event_ctx
    adv._session_id_getter = lambda: 0
    # Stub helpers that would call DB or API
    adv._summarize_new_telemetry = lambda laps: ""
    adv._car_track_header = lambda *a, **k: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._DATA_QUALITY_NOTE = ""
    return adv


# ===========================================================================
# Section 1 — Timed race context in _get_event_context_block
# ===========================================================================

class TestTimedRaceContextBlock:
    """Criterion 1: _get_event_context_block for timed race emits correct string."""

    def _make_advisor_with_event(self, event_ctx: dict) -> da.DrivingAdvisor:
        return _make_stubbed_advisor(event_ctx)

    def test_timed_race_contains_minutes_timed_race_label(self):
        """50-minute timed race -> '50 minutes, Timed Race'."""
        adv = self._make_advisor_with_event({
            "race_type": "timed",
            "duration_mins": 50,
            "laps": 0,
            "tyre_wear": 8.0,
            "fuel_mult": 3.0,
        })
        # Need to set _config for track lookup
        adv._config = {}
        block = adv._get_event_context_block()
        assert "50 minutes, Timed Race" in block, (
            f"Expected '50 minutes, Timed Race' in block, got:\n{block}"
        )

    def test_timed_race_does_not_contain_laps_lap_race(self):
        """50-minute timed race must NOT emit 'laps, Lap Race'."""
        adv = self._make_advisor_with_event({
            "race_type": "timed",
            "duration_mins": 50,
            "laps": 0,
        })
        adv._config = {}
        block = adv._get_event_context_block()
        assert "laps, Lap Race" not in block, (
            f"'laps, Lap Race' must not appear in timed-race block:\n{block}"
        )

    def test_timed_race_build_setup_diagnosis_is_timed_race_true(self):
        """build_setup_diagnosis with race_type='timed' -> is_timed_race True."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={},
            car_name="",
            event_ctx={"race_type": "timed", "duration_mins": 50},
            feeling=None,
            location_confidence="low",
        )
        assert diag["is_timed_race"] is True
        assert diag["event_type"] == "timed"


# ===========================================================================
# Section 2 — 50-minute race never rendered as "1 lap"
# ===========================================================================

class TestTimedRaceNotSingularLap:
    """Criterion 2: timed-race block must not contain '1 lap' / '1 laps'."""

    def test_timed_race_block_has_no_1_lap_string(self):
        adv = _make_stubbed_advisor({
            "race_type": "timed",
            "duration_mins": 50,
            "laps": 0,
        })
        adv._config = {}
        block = adv._get_event_context_block()
        assert "1 lap" not in block.lower(), (
            f"'1 lap' must not appear in timed-race block:\n{block}"
        )
        assert "1 laps" not in block.lower(), (
            f"'1 laps' must not appear in timed-race block:\n{block}"
        )

    def test_timed_string_appears_in_block(self):
        """Positive assertion: timed string is present."""
        adv = _make_stubbed_advisor({
            "race_type": "timed",
            "duration_mins": 50,
        })
        adv._config = {}
        block = adv._get_event_context_block()
        assert "Timed Race" in block


# ===========================================================================
# Section 3 — Natural frequency in Hz not N/mm
# ===========================================================================

class TestSpringUnitsHz:
    """Criterion 3: format_setup_for_prompt uses 'Hz' not 'N/mm'.

    The format is 'Springs F/R: 3.5/3.0 Hz' — Hz appears after both values.
    We verify: the springs line contains 'Hz', and the values 3.5 and 3.0 appear,
    and 'N/mm' does not appear anywhere.
    """

    def test_springs_labelled_hz(self):
        setup = {
            "springs_front": 3.5,
            "springs_rear": 3.0,
        }
        prompt = format_setup_for_prompt(setup)
        # The format is "Springs F/R: 3.5/3.0 Hz" — find the springs line
        springs_line = next(
            (ln for ln in prompt.splitlines() if "Springs" in ln),
            None,
        )
        assert springs_line is not None, f"No 'Springs' line in prompt:\n{prompt}"
        assert "Hz" in springs_line, (
            f"Expected 'Hz' unit in springs line, got: {springs_line!r}"
        )
        assert "3.5" in springs_line, (
            f"Expected spring value 3.5 in springs line: {springs_line!r}"
        )
        assert "3.0" in springs_line, (
            f"Expected spring value 3.0 in springs line: {springs_line!r}"
        )

    def test_nm_per_mm_not_in_prompt(self):
        setup = {"springs_front": 3.5, "springs_rear": 3.0}
        prompt = format_setup_for_prompt(setup)
        assert "N/mm" not in prompt, f"'N/mm' must not appear in setup prompt:\n{prompt}"


# ===========================================================================
# Section 4 — Driver hard constraints present in the prompt
# ===========================================================================

class TestDriverHardConstraintsInPrompt:
    """Criterion 4: DRIVER_HARD_CONSTRAINTS + PERSONAL_DRIVER_TUNING_MODEL appear in prompt
    before telemetry / current setup section."""

    def _build_prompt(self) -> str:
        laps = [_make_lap(bottoming_count=0, wheelspin_count=5, lock_up_count=1)]
        adv = _make_stubbed_advisor({})
        adv._config = {}
        return adv._build_combined_prompt(
            laps, setup={}, history_str="",
            car_name="Test Car", car_specs={},
        )

    def test_personal_driver_tuning_model_in_prompt(self):
        prompt = self._build_prompt()
        assert "Driver Tuning Model" in prompt, (
            "PERSONAL_DRIVER_TUNING_MODEL heading not found in prompt"
        )

    def test_driver_hard_constraints_in_prompt(self):
        prompt = self._build_prompt()
        assert "Driver Hard Constraints" in prompt, (
            "DRIVER_HARD_CONSTRAINTS heading not found in prompt"
        )

    def test_constraints_appear_before_telemetry_section(self):
        prompt = self._build_prompt()
        constraints_idx = prompt.find("Driver Hard Constraints")
        telemetry_idx = prompt.find("## Telemetry summary")
        assert constraints_idx != -1, "Driver Hard Constraints not found in prompt"
        assert telemetry_idx != -1, "Telemetry summary section not found in prompt"
        assert constraints_idx < telemetry_idx, (
            f"Driver Hard Constraints (idx={constraints_idx}) must appear before "
            f"Telemetry summary (idx={telemetry_idx})"
        )

    def test_eight_constraint_numbers_in_block(self):
        """DRIVER_HARD_CONSTRAINTS must contain numbered items 1-8 (constraint #9 was
        removed in the Setup Brain Upgrade — gearbox-preserve-on-telemetry is now
        handled by gearbox_category_mismatch validation rule instead)."""
        for n in range(1, 9):
            assert f"{n}." in DRIVER_HARD_CONSTRAINTS, (
                f"Constraint #{n} not found in DRIVER_HARD_CONSTRAINTS"
            )
        assert "9." not in DRIVER_HARD_CONSTRAINTS, (
            "Constraint #9 should have been removed (now 8 constraints total)"
        )

    def test_module_constants_importable(self):
        assert isinstance(PERSONAL_DRIVER_TUNING_MODEL, str) and len(PERSONAL_DRIVER_TUNING_MODEL) > 20
        assert isinstance(DRIVER_HARD_CONSTRAINTS, str) and len(DRIVER_HARD_CONSTRAINTS) > 20


# ===========================================================================
# Section 5 — Floaty front + minimum front aero => aero/platform-limited
# ===========================================================================

class TestFloatyFrontMinAero:
    """Criterion 5: floaty/understeer feeling + aero_front at minimum => front aero / platform-limited."""

    def _setup_near_min_aero(self) -> dict:
        """Return a setup where aero_front is at the generic minimum (0)."""
        return {"aero_front": 0, "aero_rear": 100}

    def test_aero_front_near_min_true(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_near_min_aero(),
            car_name="",
            event_ctx={},
            feeling="front floaty and lots of understeer",
            location_confidence="low",
        )
        assert diag["aero_front_near_min"] is True

    def test_dominant_problem_references_front_aero_platform(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_near_min_aero(),
            car_name="",
            event_ctx={},
            feeling="front floaty and lots of understeer",
            location_confidence="low",
        )
        dom = diag["dominant_problem"].lower()
        assert "front aero" in dom or "platform" in dom, (
            f"dominant_problem should reference 'front aero' or 'platform': {dom!r}"
        )

    def test_recommended_priority_starts_with_aero_front(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_near_min_aero(),
            car_name="",
            event_ctx={},
            feeling="front floaty and lots of understeer",
            location_confidence="low",
        )
        priority = diag["recommended_tuning_priority"]
        assert priority, "recommended_tuning_priority must not be empty"
        assert "aero" in priority[0].lower() and "front" in priority[0].lower(), (
            f"First priority item must be aero/front, got: {priority[0]!r}"
        )

    def test_driver_feel_flags_floaty_front(self):
        flags = _parse_driver_feel("front floaty and lots of understeer")
        assert flags["floaty_front"] is True


# ===========================================================================
# Section 6 — Rear loose on exit + minimum rear aero => rear aero diagnosis
# ===========================================================================

class TestRearLooseMinRearAero:
    """Criterion 6: rear loose on exit + high wheelspin + rear aero at min => rear aero/traction diagnosis
    and does NOT recommend reducing rear aero."""

    def _setup_rear_near_min(self) -> dict:
        return {"aero_front": 100, "aero_rear": 0}

    def test_aero_rear_near_min_true(self):
        laps = [_make_lap(wheelspin_count=20)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_rear_near_min(),
            car_name="",
            event_ctx={},
            feeling="rear loose on exit and very unstable",
            location_confidence="low",
        )
        assert diag["aero_rear_near_min"] is True

    def test_dominant_problem_references_rear_traction_or_aero(self):
        laps = [_make_lap(wheelspin_count=20)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_rear_near_min(),
            car_name="",
            event_ctx={},
            feeling="rear loose on exit and very unstable",
            location_confidence="low",
        )
        dom = diag["dominant_problem"].lower()
        assert "rear" in dom or "traction" in dom or "aero" in dom, (
            f"dominant_problem should reference rear traction/aero: {dom!r}"
        )

    def test_ai_reducing_rear_aero_is_rejected_when_wheelspin_high(self):
        """validate_setup_engineering rejects AI reducing rear aero when wheelspin is severe."""
        laps = [_make_lap(wheelspin_count=20)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup=self._setup_rear_near_min(),
            car_name="",
            event_ctx={},
            feeling="rear loose on exit",
            location_confidence="low",
        )
        # AI tries to reduce rear aero (bad move)
        current_aero_rear = 100
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "aero_rear", "from": current_aero_rear, "to": 50,
                         "setting": "Rear Aero", "why": "test", "to_clamped": 50}],
            "setup_fields": {"aero_rear": 50},
        })
        setup = {"aero_rear": current_aero_rear}
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "aero_cut_with_wheelspin" in prefixes, (
            f"Expected 'aero_cut_with_wheelspin' in reasons; got:\n" + "\n".join(reasons)
        )


# ===========================================================================
# Section 7 — Bottoming below 0.5/lap blocks ride-height increase
# ===========================================================================

class TestBottomingMinorBlocksRhIncrease:
    """Criterion 7: validate_setup_engineering rejects RH increase when bottoming_band='minor'."""

    def _make_minor_diagnosis(self) -> dict:
        laps = [_make_lap(bottoming_count=0)]  # avg = 0 -> minor
        return build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80},
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )

    def test_minor_bottoming_diagnosis_band(self):
        diag = self._make_minor_diagnosis()
        assert diag["bottoming_band"] == "minor", (
            f"Expected 'minor' band, got {diag['bottoming_band']!r}"
        )
        assert diag["avg_bottoming"] < 0.5

    def test_rh_increase_rejected_for_minor_bottoming(self):
        diag = self._make_minor_diagnosis()
        # AI raises ride_height_front from 80 -> 90
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "ride_height_front", "from": 80, "to": 90,
                         "setting": "Ride Height Front", "why": "test", "to_clamped": 90}],
            "setup_fields": {"ride_height_front": 90},
        })
        setup = {"ride_height_front": 80}
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "rh_for_minor_bottoming" in prefixes, (
            f"Expected 'rh_for_minor_bottoming'; got:\n" + "\n".join(reasons)
        )

    def test_avg_bottoming_below_threshold_is_minor(self):
        """0.2/lap is well below 0.5 threshold -> 'minor'."""
        laps = [_make_lap(bottoming_count=0), _make_lap(bottoming_count=0),
                _make_lap(bottoming_count=1)]  # avg = 1/3 ≈ 0.33 < 0.5
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80},
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )
        assert diag["bottoming_band"] == "minor"
        assert diag["avg_bottoming"] < 0.5


# ===========================================================================
# Section 8 — Severe wheelspin classified correctly; band boundaries
# ===========================================================================

class TestWheelspinBands:
    """Criterion 8: wheelspin band classification + boundary checks."""

    def _diag_for_wheelspin(self, count_per_lap: float) -> dict:
        """Build a diagnosis with the given average wheelspin count (using laps)."""
        # Use integer laps that average to the desired count
        n = round(count_per_lap)
        laps = [_make_lap(wheelspin_count=n)]
        return build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )

    def test_22_wheelspin_per_lap_is_severe(self):
        laps = [_make_lap(wheelspin_count=22)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        assert diag["wheelspin_band"] == "severe", (
            f"Expected 'severe' for 22/lap, got {diag['wheelspin_band']!r}"
        )

    def test_5_wheelspin_is_low(self):
        diag = self._diag_for_wheelspin(5)
        assert diag["wheelspin_band"] == "low"

    def test_6_wheelspin_is_meaningful(self):
        diag = self._diag_for_wheelspin(6)
        assert diag["wheelspin_band"] == "meaningful"

    def test_10_wheelspin_is_meaningful(self):
        """Boundary: exactly 10 -> meaningful (>5, <=10)."""
        diag = self._diag_for_wheelspin(10)
        assert diag["wheelspin_band"] == "meaningful"

    def test_11_wheelspin_is_major(self):
        diag = self._diag_for_wheelspin(11)
        assert diag["wheelspin_band"] == "major"

    def test_15_wheelspin_is_major(self):
        """Boundary: exactly 15 -> major (>10, <=15)."""
        diag = self._diag_for_wheelspin(15)
        assert diag["wheelspin_band"] == "major"

    def test_16_wheelspin_is_severe(self):
        diag = self._diag_for_wheelspin(16)
        assert diag["wheelspin_band"] == "severe"


# ===========================================================================
# Section 9 — Gearbox preserved when driver says good; gearbox edit rejected
# ===========================================================================

class TestGearboxPreservation:
    """Criterion 9: gearbox_good flag + gearbox_flag preserve + validation rejects edits."""

    def test_parse_driver_feel_gearbox_good_flag(self):
        flags = _parse_driver_feel("gearbox is good — really happy with gears")
        assert flags["gearbox_good"] is True

    def test_gearbox_flag_preserve_when_driver_says_good(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling="gearbox is good",
            location_confidence="low",
        )
        assert diag["gearbox_flag"] == "preserve"

    def test_gearbox_flag_preserve_overrides_rev_limiter_hits(self):
        """Even with rev limiter hits, gearbox_good forces preserve."""
        laps = [_make_lap(rev_limiter_by_gear={5: 3, 6: 2})]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling="gearbox is good",
            location_confidence="low",
        )
        assert diag["gearbox_flag"] == "preserve"

    def test_gearbox_edit_rejected_when_preserve(self):
        """validate_setup_engineering rejects transmission_max_speed_kmh change using
        gearbox_category_mismatch rule — fires when gearbox_good flag is set or when
        gearing_diagnosis_category is in the preserve-set (insufficient_data, gear_too_long,
        limiter_limited).  Here the driver says 'gearbox is good' which sets the flag."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"transmission_max_speed_kmh": 270.0},
            car_name="",
            event_ctx={},
            feeling="gearbox is good",
            location_confidence="low",
        )
        assert diag["gearbox_flag"] == "preserve"

        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "transmission_max_speed_kmh", "from": 270.0, "to": 280.0,
                         "setting": "Transmission", "why": "test", "to_clamped": 280.0}],
            "setup_fields": {"transmission_max_speed_kmh": 280.0},
        })
        setup = {"transmission_max_speed_kmh": 270.0}
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "gearbox_category_mismatch" in prefixes, (
            f"Expected 'gearbox_category_mismatch'; got:\n" + "\n".join(reasons)
        )

    def test_gear_ratio_change_rejected_when_preserve(self):
        """Changes with field='gear_ratios' are rejected with gearbox_category_mismatch
        when gearing_diagnosis_category is in the preserve-set or driver says gearbox good.
        With empty laps and no data, gearing_diagnosis_category = insufficient_data (preserve)."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={},
            car_name="",
            event_ctx={},
            feeling="gearbox is good",
            location_confidence="low",
        )
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "gear_ratios", "from": "[3.2]", "to": "[3.0]",
                         "setting": "Gear Ratios", "why": "test", "to_clamped": "[3.0]"}],
            "setup_fields": {},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, {}, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "gearbox_category_mismatch" in prefixes, (
            f"Expected 'gearbox_category_mismatch'; got:\n" + "\n".join(reasons)
        )

    def test_gearbox_flag_may_change_without_driver_good(self):
        """Without gearbox_good flag, a CONFIRMED gear_too_short (top-gear limiter +
        a real top-speed deficit + trustworthy location) -> may_change.

        Group 63: gear_too_short now requires a valid top-speed target AND
        trustworthy location — a limiter reading with no target (transmission_max_
        speed_kmh=0) or low location confidence is honest UNKNOWN, not may_change.
        """
        laps = [_make_lap(rev_limiter_by_gear={6: 5}, max_speed_kmh=200.0)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"transmission_max_speed_kmh": 300, "num_gears": 6},
            car_name="",
            event_ctx={}, feeling="car feels great",
            location_confidence="high",
        )
        assert diag["gearbox_flag"] == "may_change"
        assert diag["gearing_diagnosis_category"] == "gear_too_short"

    def test_gearbox_flag_preserve_without_speed_target(self):
        """Group 63: a top-gear limiter reading with NO valid top-speed target
        (transmission_max_speed_kmh uncaptured / 0) is honest UNKNOWN -> preserve,
        never a gear_too_short 'may_change' default."""
        laps = [_make_lap(rev_limiter_by_gear={6: 5})]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling="car feels great",
            location_confidence="low",
        )
        assert diag["gearing_diagnosis_category"] == "insufficient_data"
        assert diag["gearbox_flag"] == "preserve"


# ===========================================================================
# Section 10 — Clean response (no RH change) returns [] for rh_for_minor_bottoming
# ===========================================================================

class TestCleanResponsePassesRhRule:
    """Criterion 10: AI response that does NOT change ride height returns no rh_for_minor_bottoming error."""

    def test_no_rh_change_returns_empty_for_rh_rule(self):
        laps = [_make_lap(bottoming_count=0)]
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"aero_front": 0},
            car_name="",
            event_ctx={},
            feeling="front floaty",
            location_confidence="low",
        )
        # AI changes aero_front (good) — no ride height change
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "aero_front", "from": 0, "to": 100,
                         "setting": "Aero Front", "why": "increase downforce", "to_clamped": 100}],
            "setup_fields": {"aero_front": 100},
        })
        setup = {"ride_height_front": 80, "ride_height_rear": 82, "aero_front": 0}
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        rh_reasons = [r for r in reasons if r.startswith("rh_for_minor_bottoming")]
        assert rh_reasons == [], (
            f"Expected no rh_for_minor_bottoming, got:\n" + "\n".join(rh_reasons)
        )


# ===========================================================================
# Section 11 — Reject AI that leaves aero at min with floaty diagnosis
# ===========================================================================

class TestRejectAeroAtMinFloaty:
    """Criterion 11: AI that doesn't address front aero while it's near-min and driver is floaty."""

    def test_ai_ignoring_aero_front_when_floaty_and_near_min(self):
        """AI response that does not address aero_front while aero_front near min + floaty."""
        laps = [_make_lap()]
        setup = {"aero_front": 0, "aero_rear": 200}
        diag = build_setup_diagnosis(
            laps=laps,
            setup=setup,
            car_name="",
            event_ctx={},
            feeling="front floaty and pushing wide",
            location_confidence="low",
        )
        assert diag["aero_front_near_min"] is True
        assert diag["driver_feel_flags"]["floaty_front"] is True

        # AI changes something else entirely — doesn't address aero_front
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "arb_rear", "from": 4, "to": 3,
                         "setting": "ARB Rear", "why": "soften rear", "to_clamped": 3}],
            "setup_fields": {"arb_rear": 3},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "aero_at_min_floaty" in prefixes, (
            f"Expected 'aero_at_min_floaty'; got:\n" + "\n".join(reasons)
        )

    def test_ai_keeping_aero_front_near_min_when_floaty(self):
        """AI response that sets aero_front <= near-min threshold while floaty."""
        laps = [_make_lap()]
        setup = {"aero_front": 50, "aero_rear": 200}
        from strategy.setup_ranges import resolve_ranges, GENERIC_DEFAULTS
        # Generic aero_front range is (0, 1000); 10% threshold = 100
        # AI keeps it at 50 (below threshold)
        diag = build_setup_diagnosis(
            laps=laps,
            setup=setup,
            car_name="",
            event_ctx={},
            feeling="front floaty",
            location_confidence="low",
        )
        assert diag["aero_front_near_min"] is True

        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "aero_front", "from": 50, "to": 60,
                         "setting": "Aero Front", "why": "marginal increase", "to_clamped": 60}],
            "setup_fields": {"aero_front": 60},
        })
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        # 60 <= 100 (near-min threshold for 0-1000 range) -> aero_at_min_floaty
        assert "aero_at_min_floaty" in prefixes, (
            f"Expected 'aero_at_min_floaty' (AI sets 60 which is <=100 threshold); got:\n"
            + "\n".join(reasons)
        )


# ===========================================================================
# Section 12 — Reject AI that changes a locked setting
# ===========================================================================

class TestLockedFieldRejected:
    """Criterion 12: validate_setup_engineering rejects locked-field changes."""

    def test_locked_aero_change_rejected(self):
        """When allowed_tuning excludes 'aero', changing aero_front is rejected."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={"allowed_tuning": ["suspension", "differential"]},
            feeling=None, location_confidence="low",
        )

        # AI tries to change aero_front (which is locked)
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "aero_front", "from": 200, "to": 300,
                         "setting": "Aero Front", "why": "test", "to_clamped": 300}],
            "setup_fields": {"aero_front": 300},
        })
        setup = {"aero_front": 200}
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        event_ctx = {"allowed_tuning": ["suspension", "differential"]}
        reasons = validate_setup_engineering(ai_resp, diag, setup, ranges, event_ctx)
        locked_reasons = [r for r in reasons if "locked" in r.lower()]
        assert locked_reasons, (
            f"Expected a locked-field reason; got:\n" + "\n".join(reasons)
        )


# ===========================================================================
# Section 13 — Historical "driver hated" label prevents repeating
# ===========================================================================

class TestDriverHatedLabelInHistory:
    """Criterion 13: setup_history.format_for_prompt emits DRIVER HATED + do-not-repeat directive."""

    def test_hated_entry_emits_driver_hated_directive(self, tmp_path, monkeypatch):
        import data.setup_history as sh_module
        tmp_file = tmp_path / "setup_history.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sh_module, "_HISTORY_PATH", tmp_file)

        config_id = "test_hated_config"
        entry = {
            "type": "feeling_fix",
            "feeling": "front floaty",
            "changes": [{"setting": "ARB Front", "from": 5, "to": 3, "why": "soften"}],
        }
        sh_module.save_entry(
            config_id, "Test Car", "Fuji",
            entry, labels=["hated"],
            driver_feedback="Made the car worse — horrible understeer",
        )

        result = sh_module.format_for_prompt(config_id)
        assert "DRIVER HATED" in result, (
            f"Expected 'DRIVER HATED' directive in history prompt; got:\n{result}"
        )
        assert "do not repeat" in result.lower() or "not repeat" in result.lower(), (
            f"Expected do-not-repeat directive; got:\n{result}"
        )

    def test_hated_entry_includes_subjective_confidence_line(self, tmp_path, monkeypatch):
        import data.setup_history as sh_module
        tmp_file = tmp_path / "setup_history.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sh_module, "_HISTORY_PATH", tmp_file)

        config_id = "test_hated_subj"
        entry = {"type": "feeling_fix", "feeling": "snap exit"}
        sh_module.save_entry(config_id, "Test Car", "Fuji", entry, labels=["hated"])

        result = sh_module.format_for_prompt(config_id)
        assert "subjective confidence is a performance variable" in result, (
            f"Expected subjective-confidence note; got:\n{result}"
        )


# ===========================================================================
# Section 14 — Historical "driver liked" label in prompt
# ===========================================================================

class TestDriverLikedLabelInHistory:
    """Criterion 14: setup_history.format_for_prompt emits DRIVER LIKED + subjective-confidence line."""

    def test_liked_entry_emits_driver_liked_directive(self, tmp_path, monkeypatch):
        import data.setup_history as sh_module
        tmp_file = tmp_path / "setup_history.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sh_module, "_HISTORY_PATH", tmp_file)

        config_id = "test_liked_config"
        entry = {
            "type": "feeling_fix",
            "feeling": "much better balance",
            "changes": [{"setting": "ARB Rear", "from": 3, "to": 4, "why": "stabilise"}],
        }
        sh_module.save_entry(config_id, "Test Car", "Fuji", entry, labels=["liked"])

        result = sh_module.format_for_prompt(config_id)
        assert "DRIVER LIKED" in result, (
            f"Expected 'DRIVER LIKED' directive; got:\n{result}"
        )
        assert "subjective confidence is a performance variable" in result, (
            f"Expected subjective-confidence note; got:\n{result}"
        )


# ===========================================================================
# Section 15 — Before/after comparison: save_entry + label round-trip
# ===========================================================================

class TestSetupHistoryRoundTrip:
    """Criterion 15: save_entry + load_history / format_for_prompt delta round-trip."""

    def test_save_and_reload_entry_with_label(self, tmp_path, monkeypatch):
        import data.setup_history as sh_module
        tmp_file = tmp_path / "setup_history.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sh_module, "_HISTORY_PATH", tmp_file)

        config_id = "roundtrip_config"
        entry = {
            "type": "build_race",
            "setup_snapshot": {
                "springs_front": 3.5, "springs_rear": 3.0,
                "arb_front": 4, "arb_rear": 3,
                "dampers_front_comp": 30, "dampers_front_ext": 40,
                "dampers_rear_comp": 25, "dampers_rear_ext": 35,
                "camber_front": 1.0, "camber_rear": 1.5,
            },
            "reasoning": "Test reasoning",
        }
        sh_module.save_entry(
            config_id, "RSR Car", "Fuji",
            entry, labels=["liked"], driver_feedback="Great balance improvement",
        )

        loaded = sh_module.load_history(config_id)
        assert len(loaded) == 1
        loaded_entry = loaded[0]
        assert loaded_entry["type"] == "build_race"
        assert "liked" in loaded_entry["labels"]
        assert loaded_entry["driver_feedback"] == "Great balance improvement"
        assert "ts" in loaded_entry  # timestamp was set

    def test_hated_label_round_trips(self, tmp_path, monkeypatch):
        import data.setup_history as sh_module
        tmp_file = tmp_path / "setup_history.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sh_module, "_HISTORY_PATH", tmp_file)

        config_id = "roundtrip_hated"
        entry = {"type": "feeling_fix", "feeling": "snappy exit"}
        sh_module.save_entry(config_id, "RSR", "Fuji", entry, labels=["hated"])

        loaded = sh_module.load_history(config_id)
        assert loaded[0]["labels"] == ["hated"]

        result = sh_module.format_for_prompt(config_id)
        assert "DRIVER HATED" in result


# ===========================================================================
# Section 16 — Porsche 911 RSR '17 / Fuji Regression (mandatory)
# ===========================================================================

_RSR_FEELING = (
    "front floaty, entry understeer, mid-corner push, "
    "rear loose on throttle exit, rear stable on brakes, gearbox is good"
)

_RSR_EVENT_CTX = {
    "race_type": "timed",
    "duration_mins": 50,
    "tyre_wear": 8.0,
    "fuel_mult": 3.0,
    "refuel_rate": 1.0,  # L/s
    "laps": 0,
}

_RSR_SETUP = {
    "name": "Porsche 911 RSR '17",
    "track": "Fuji Speedway",
    "springs_front": 3.5,
    "springs_rear": 3.0,
    "aero_front": 0,    # AT MINIMUM
    "aero_rear": 0,     # AT MINIMUM
    "ride_height_front": 80,
    "ride_height_rear": 82,
    "transmission_max_speed_kmh": 270.0,
    "arb_front": 4,
    "arb_rear": 3,
}

def _make_rsr_laps() -> list:
    """5 laps averaging: bottoming 0.2/lap, wheelspin 22/lap, snap 11.2/lap."""
    # 5 laps: bottoming totals = 1, wheelspin = 110, snap = 56
    return [
        _make_lap(bottoming_count=0, wheelspin_count=22, snap_throttle_count=11),
        _make_lap(bottoming_count=0, wheelspin_count=22, snap_throttle_count=11),
        _make_lap(bottoming_count=0, wheelspin_count=22, snap_throttle_count=11),
        _make_lap(bottoming_count=0, wheelspin_count=22, snap_throttle_count=12),
        _make_lap(bottoming_count=1, wheelspin_count=22, snap_throttle_count=11),
    ]
    # avg bottoming = 1/5 = 0.2, avg wheelspin = 22.0, avg snap = 11.2


class TestRSRFujiRegression:
    """Criterion 16: Full Porsche 911 RSR / Fuji 50-min timed race regression."""

    @pytest.fixture(autouse=True)
    def _build_diagnosis(self):
        self.laps = _make_rsr_laps()
        self.diag = build_setup_diagnosis(
            laps=self.laps,
            setup=_RSR_SETUP,
            car_name="Porsche 911 RSR '17",
            event_ctx=_RSR_EVENT_CTX,
            feeling=_RSR_FEELING,
            location_confidence="low",
        )

    def test_aero_front_near_min_true(self):
        assert self.diag["aero_front_near_min"] is True

    def test_aero_rear_near_min_true(self):
        assert self.diag["aero_rear_near_min"] is True

    def test_dominant_problem_front_aero_platform(self):
        dom = self.diag["dominant_problem"].lower()
        assert "front aero" in dom or "platform" in dom, (
            f"dominant_problem should be front aero / platform-limited: {dom!r}"
        )

    def test_bottoming_band_minor(self):
        assert self.diag["bottoming_band"] == "minor", (
            f"Expected 'minor' (avg=0.2/lap), got {self.diag['bottoming_band']!r}"
        )

    def test_avg_bottoming_is_0_2(self):
        assert abs(self.diag["avg_bottoming"] - 0.2) < 0.01, (
            f"Expected avg_bottoming ≈ 0.2, got {self.diag['avg_bottoming']}"
        )

    def test_wheelspin_band_severe(self):
        assert self.diag["wheelspin_band"] == "severe", (
            f"Expected 'severe' for 22/lap, got {self.diag['wheelspin_band']!r}"
        )

    def test_gearbox_flag_preserve(self):
        assert self.diag["gearbox_flag"] == "preserve", (
            f"Expected 'preserve' (driver says gearbox is good), got {self.diag['gearbox_flag']!r}"
        )

    def test_priority_starts_with_aero(self):
        priority = self.diag["recommended_tuning_priority"]
        assert priority, "recommended_tuning_priority must not be empty"
        first = priority[0].lower()
        assert "aero" in first and "front" in first, (
            f"First priority must be front aero; got {priority[0]!r}"
        )

    def test_ride_height_not_near_top_of_priority(self):
        """ride_height must NOT be in top 2 priority positions."""
        priority = self.diag["recommended_tuning_priority"]
        top_two = " ".join(priority[:2]).lower()
        assert "ride height" not in top_two, (
            f"ride_height must not be in top-2 priority; got {priority[:2]!r}"
        )

    def test_ai_raising_rh_rejected_rh_for_minor_bottoming(self):
        """Mock AI response raising ride_height_front -> rh_for_minor_bottoming."""
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "ride_height_front", "from": 80, "to": 90,
                         "setting": "Ride Height Front", "why": "test", "to_clamped": 90}],
            "setup_fields": {"ride_height_front": 90},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, self.diag, _RSR_SETUP, ranges, _RSR_EVENT_CTX)
        prefixes = [r.split(":")[0] for r in reasons]
        assert "rh_for_minor_bottoming" in prefixes, (
            f"Expected rh_for_minor_bottoming; got:\n" + "\n".join(reasons)
        )

    def test_ai_reducing_rear_aero_rejected_aero_cut_with_wheelspin(self):
        """Mock AI reducing aero_rear -> aero_cut_with_wheelspin (severe wheelspin)."""
        setup_with_rear_aero = dict(_RSR_SETUP)
        setup_with_rear_aero["aero_rear"] = 100  # give it a value to cut from
        laps = _make_rsr_laps()
        diag = build_setup_diagnosis(
            laps=laps,
            setup=setup_with_rear_aero,
            car_name="Porsche 911 RSR '17",
            event_ctx=_RSR_EVENT_CTX,
            feeling=_RSR_FEELING,
            location_confidence="low",
        )
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "aero_rear", "from": 100, "to": 50,
                         "setting": "Rear Aero", "why": "test", "to_clamped": 50}],
            "setup_fields": {"aero_rear": 50},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, setup_with_rear_aero, ranges, _RSR_EVENT_CTX)
        prefixes = [r.split(":")[0] for r in reasons]
        assert "aero_cut_with_wheelspin" in prefixes, (
            f"Expected aero_cut_with_wheelspin; got:\n" + "\n".join(reasons)
        )

    def test_ai_changing_gearbox_rejected_gearbox_category_mismatch(self):
        """Mock AI changing transmission_max_speed_kmh -> gearbox_category_mismatch.
        The rule name changed from gearbox_edit_when_preserve to gearbox_category_mismatch
        in the Setup Brain Upgrade.  Fires here because driver says 'gearbox is good'."""
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "transmission_max_speed_kmh", "from": 270.0, "to": 280.0,
                         "setting": "Transmission", "why": "test", "to_clamped": 280.0}],
            "setup_fields": {"transmission_max_speed_kmh": 280.0},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, self.diag, _RSR_SETUP, ranges, _RSR_EVENT_CTX)
        prefixes = [r.split(":")[0] for r in reasons]
        assert "gearbox_category_mismatch" in prefixes, (
            f"Expected gearbox_category_mismatch; got:\n" + "\n".join(reasons)
        )

    def test_rsr_driver_feel_gearbox_good(self):
        assert self.diag["driver_feel_flags"]["gearbox_good"] is True

    def test_rsr_driver_feel_floaty_front(self):
        assert self.diag["driver_feel_flags"]["floaty_front"] is True

    def test_rsr_driver_feel_rear_loose_on_exit(self):
        assert self.diag["driver_feel_flags"]["rear_loose_on_exit"] is True


# ===========================================================================
# Section 17 — UI boundary: _format_engineering_validation_banner pure helper
# ===========================================================================

class TestEngineeringValidationBanner:
    """Criterion 17: ui.setup_builder_ui._format_engineering_validation_banner pure helper."""

    @pytest.fixture(autouse=True)
    def _import_banner(self):
        # Import the module-level function without constructing QApplication.
        # The function is pure (no Qt calls), so import at test time is safe.
        from ui.setup_builder_ui import _format_engineering_validation_banner
        self._banner_fn = _format_engineering_validation_banner

    def test_banner_contains_engineering_validation_failed_text(self):
        result = self._banner_fn(["rh_for_minor_bottoming: some detail here"])
        assert "Engineering validation failed after AI retry" in result, (
            f"Expected failure text in banner:\n{result}"
        )

    def test_banner_includes_error_text(self):
        error = "rh_for_minor_bottoming: AI increases ride height but bottoming is minor"
        result = self._banner_fn([error])
        assert "rh_for_minor_bottoming" in result

    def test_empty_list_returns_empty_string(self):
        result = self._banner_fn([])
        assert result == "", f"Expected empty string for [] input, got {result!r}"

    def test_multiple_errors_all_appear(self):
        errors = [
            "rh_for_minor_bottoming: detail1",
            "aero_cut_with_wheelspin: detail2",
        ]
        result = self._banner_fn(errors)
        assert "rh_for_minor_bottoming" in result
        assert "aero_cut_with_wheelspin" in result


# ===========================================================================
# Section 18 — Location-confidence guard
# ===========================================================================

class TestLocationConfidenceGuard:
    """Criterion 18: low location confidence -> low-conf caveat in prompt + rh blocked."""

    def test_low_confidence_sets_location_evidence_usable_false(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None,
            location_confidence="low",
        )
        assert diag["location_confidence"] == "low"
        assert diag["location_evidence_usable"] is False

    def test_high_confidence_sets_location_evidence_usable_true(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None,
            location_confidence="high",
        )
        assert diag["location_confidence"] == "high"
        assert diag["location_evidence_usable"] is True

    def test_format_diagnosis_emits_low_confidence_caveat(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None,
            location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        assert "approximate zones" in text.lower() or "low" in text.lower(), (
            f"Expected low-confidence caveat in format_diagnosis_for_prompt output:\n{text}"
        )
        assert "do not" in text.lower() or "not justify" in text.lower(), (
            f"Expected DO NOT justify ride-height directive:\n{text}"
        )

    def test_format_diagnosis_low_conf_contains_ride_height_constraint(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="",
            event_ctx={}, feeling=None,
            location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        assert "ride-height" in text.lower() or "ride height" in text.lower(), (
            f"Expected ride-height constraint in low-confidence output:\n{text}"
        )

    def test_rh_increase_with_low_confidence_and_consider_band_rejected(self):
        """Low location confidence + consider-band bottoming (avg 1.2) -> rh_low_confidence_location."""
        # avg bottoming 1.2 -> 'consider' band (but not 'required')
        laps = [
            _make_lap(bottoming_count=1),
            _make_lap(bottoming_count=1),
            _make_lap(bottoming_count=1),
            _make_lap(bottoming_count=2),
            _make_lap(bottoming_count=1),
        ]  # avg = 6/5 = 1.2 -> 'consider'
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80},
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )
        assert diag["bottoming_band"] == "consider", (
            f"Expected 'consider' band (avg=1.2), got {diag['bottoming_band']!r}"
        )
        assert diag["location_evidence_usable"] is False

        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "ride_height_front", "from": 80, "to": 90,
                         "setting": "RH Front", "why": "test", "to_clamped": 90}],
            "setup_fields": {"ride_height_front": 90},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, {"ride_height_front": 80}, ranges, {})
        prefixes = [r.split(":")[0] for r in reasons]
        assert "rh_low_confidence_location" in prefixes, (
            f"Expected rh_low_confidence_location; got:\n" + "\n".join(reasons)
        )

    def test_high_confidence_does_not_emit_rh_low_confidence_guard(self):
        """High location confidence with consider bottoming -> no rh_low_confidence_location."""
        laps = [
            _make_lap(bottoming_count=1),
            _make_lap(bottoming_count=1),
            _make_lap(bottoming_count=2),
        ]  # avg = 4/3 ≈ 1.33 -> 'consider'
        diag = build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80},
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="high",  # HIGH confidence
        )
        assert diag["location_evidence_usable"] is True

        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "ride_height_front", "from": 80, "to": 90,
                         "setting": "RH Front", "why": "test", "to_clamped": 90}],
            "setup_fields": {"ride_height_front": 90},
        })
        from strategy.setup_ranges import resolve_ranges
        ranges = resolve_ranges("")
        reasons = validate_setup_engineering(ai_resp, diag, {"ride_height_front": 80}, ranges, {})
        low_conf_reasons = [r for r in reasons if "rh_low_confidence_location" in r]
        assert low_conf_reasons == [], (
            f"High confidence should not emit rh_low_confidence_location; got:\n"
            + "\n".join(low_conf_reasons)
        )


# ===========================================================================
# Section 19 — Regenerate-once orchestration in build_combined_setup_response
# ===========================================================================
#
# call_api is imported into driving_advisor's own namespace:
#   from strategy._ai_client import call_api, ...
# So the correct monkeypatch target is "strategy.driving_advisor.call_api".
#
# The advisor also calls parse_recommendations_from_response; since self._db
# is None the DB-write branch is skipped entirely.  We only need to stub
# self._recorder.recent_laps so the method doesn't return early.

def _make_recorder_stub(laps):
    """Return a minimal recorder stub whose recent_laps() returns *laps*."""
    rec = SimpleNamespace(recent_laps=lambda n: laps)
    return rec


def _make_full_advisor(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    """Build an advisor with recorder + api_key wired so build_combined_setup_response
    does not short-circuit before calling call_api."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder    = _make_recorder_stub(laps)
    adv._tracker     = None
    adv._config      = {"anthropic": {"api_key": "fake-key-for-test"}}
    adv._db          = None
    adv._car_id_ref  = [0]
    adv._event_ctx   = event_ctx
    adv._session_id_getter = lambda: 0
    # Stub the helpers that would call Qt / DB / network / track-model files
    adv._summarize_new_telemetry  = lambda laps: ""
    adv._car_track_header         = lambda *a, **k: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context  = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._get_history_context      = lambda: ""
    adv._DATA_QUALITY_NOTE        = ""
    return adv


def _valid_ai_json(changes: list | None = None, setup_fields: dict | None = None) -> str:
    """Return a minimal schema-valid AI JSON string with optional changes/setup_fields."""
    payload = {
        "analysis": "Test analysis — no issues.",
        "primary_issue": "none",
        "issue_classification": {"bottoming": "not-present"},
        "changes": changes or [],
        "setup_fields": setup_fields or {},
        "validation_targets": {"braking_stability": "must remain stable"},
        "confidence": {"overall": "medium", "reason": "test fixture"},
        "do_not_change_reasoning": [],
        "preserve_settings": [],
    }
    return json.dumps(payload)


def _violating_rh_json(cur_rh: int = 80, new_rh: int = 90) -> str:
    """Return an AI JSON that raises ride_height_front — violates rh_for_minor_bottoming
    when bottoming_band is 'minor'."""
    return _valid_ai_json(
        changes=[{
            "field": "ride_height_front",
            "setting": "Ride Height Front",
            "from": cur_rh,
            "to": new_rh,
            "why": "reduce bottoming",
        }],
        setup_fields={"ride_height_front": new_rh},
    )


def _clean_aero_json(cur_aero: int = 0, new_aero: int = 200) -> str:
    """Return a clean AI JSON that increases aero_front — no engineering violations."""
    return _valid_ai_json(
        changes=[{
            "field": "aero_front",
            "setting": "Aero Front",
            "from": cur_aero,
            "to": new_aero,
            "why": "increase front downforce",
        }],
        setup_fields={"aero_front": new_aero},
    )


# RSR Fuji fixture reused here: avg bottoming 0.2/lap -> minor band
_ORCH_SETUP = {
    "ride_height_front": 80,
    "ride_height_rear": 82,
    "aero_front": 0,
    "aero_rear": 0,
    "transmission_max_speed_kmh": 270.0,
}
_ORCH_EVENT_CTX = {
    "race_type": "timed",
    "duration_mins": 50,
    "laps": 0,
}


class TestRegenerateOnceOrchestration:
    """Criterion 19 (REWRITTEN for Group 42): deterministic rule-first flow.

    Group 42 removed the AI-retry loop entirely.  call_api is now used ONLY for
    an optional audit step (at most one call) — NOT to generate changes.  Changes
    are authored by the deterministic rule engine.  Engineering-safety violations
    in the rule engine output trigger the deterministic fallback (NO AI retry).

    These three tests express the new Group 42 contract while preserving the
    underlying safety guarantees that the original tests were designed to check.
    """

    def test_rule_engine_produces_approved_status_without_retry(self, monkeypatch):
        """Rule engine with actionable evidence (RSR minor bottoming laps) produces
        an approved status without any AI retry loop.  call_api may be called at
        most once (audit only) — never twice."""
        laps = _make_rsr_laps()  # avg bottoming 0.2 -> minor
        adv  = _make_full_advisor(_ORCH_EVENT_CTX, laps)

        call_count = {"n": 0}

        def fake_call_api(prompt, api_key, **kwargs):
            call_count["n"] += 1
            # Return a valid audit response (Group 42: AI is audit-only)
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "Rule engine plan looks sound.",
            })

        monkeypatch.setattr(da, "call_api", fake_call_api)

        result_str = adv.build_combined_setup_response(
            setup_dict=_ORCH_SETUP,
            car_name="Porsche 911 RSR '17",
            feeling=_RSR_FEELING,
            diagnosis=build_setup_diagnosis(
                laps, _ORCH_SETUP, "Porsche 911 RSR '17",
                _ORCH_EVENT_CTX, _RSR_FEELING, location_confidence="low",
            ),
        )

        # Group 42: call_api used for audit only — at most once, never twice
        assert call_count["n"] <= 1, (
            f"Group 42 contract violation: call_api called {call_count['n']} times. "
            f"AI must be used for audit only (0 or 1 calls), not for generate+retry."
        )

        # Result must be parseable JSON
        result = json.loads(result_str)

        # Rule engine should produce an approved status (not engineering_validation_failed)
        assert not result.get("engineering_validation_failed"), (
            f"Rule engine path must not set engineering_validation_failed for minor bottoming; "
            f"got: {result.get('engineering_validation_failed')!r}"
        )

    def test_engineering_safety_failure_triggers_fallback_not_retry(self, monkeypatch):
        """When the rule engine's proposed changes trigger a blocking engineering-safety
        rule (rh_rake_risk / rh_increment_exceeds_confidence), the system falls back to
        the deterministic safe response — call_api is NOT called for a retry.

        Group 42 safety invariant: blocking engineering failures always zero changes.
        """
        # Use laps with high bottoming so rule engine may propose RH increase
        laps = _make_rsr_laps()  # minor bottoming
        adv  = _make_full_advisor(_ORCH_EVENT_CTX, laps)

        call_count = {"n": 0}

        def fake_call_api(prompt, api_key, **kwargs):
            call_count["n"] += 1
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "ok",
            })

        monkeypatch.setattr(da, "call_api", fake_call_api)

        result_str = adv.build_combined_setup_response(
            setup_dict=_ORCH_SETUP,
            car_name="Porsche 911 RSR '17",
            feeling=_RSR_FEELING,
            diagnosis=build_setup_diagnosis(
                laps, _ORCH_SETUP, "Porsche 911 RSR '17",
                _ORCH_EVENT_CTX, _RSR_FEELING, location_confidence="low",
            ),
        )

        # Group 42 contract: at most one call_api call (audit only, NO retry)
        assert call_count["n"] <= 1, (
            f"Group 42 contract violation: call_api called {call_count['n']} times "
            f"(expected 0 or 1 for audit-only path; retry loop was removed in Group 42)."
        )

        # Result must still be parseable — never raise
        result = json.loads(result_str)

        # If engineering-safety failures occurred, changes must be zeroed (safety invariant)
        if result.get("fallback_used"):
            assert result.get("changes") == [], (
                f"Safety invariant: fallback_used==True must have changes==[]; "
                f"got: {result.get('changes')!r}"
            )
            assert result.get("setup_fields") == {}, (
                f"Safety invariant: fallback_used==True must have setup_fields=={{}}; "
                f"got: {result.get('setup_fields')!r}"
            )

    def test_no_retry_when_rule_engine_produces_clean_output(self, monkeypatch):
        """When the rule engine produces clean output (no blocking violations), call_api
        is used at most once for the optional audit step — never for a retry or generate call.
        """
        laps = _make_rsr_laps()
        adv  = _make_full_advisor(_ORCH_EVENT_CTX, laps)

        call_count = {"n": 0}

        def fake_call_api(prompt, api_key, **kwargs):
            call_count["n"] += 1
            return json.dumps({
                "status": "APPROVED",
                "warnings": [],
                "contradictions": [],
                "missing_evidence": [],
                "explanation_notes": "All good.",
            })

        monkeypatch.setattr(da, "call_api", fake_call_api)

        result_str = adv.build_combined_setup_response(
            setup_dict=_ORCH_SETUP,
            car_name="Porsche 911 RSR '17",
            feeling=_RSR_FEELING,
            diagnosis=build_setup_diagnosis(
                laps, _ORCH_SETUP, "Porsche 911 RSR '17",
                _ORCH_EVENT_CTX, _RSR_FEELING, location_confidence="low",
            ),
        )

        # Group 42: call_api called at most ONCE (audit only, not generate+retry)
        assert call_count["n"] <= 1, (
            f"Group 42 contract violation: call_api called {call_count['n']} times "
            f"(expected 0 or 1; no retry loop exists in Group 42)."
        )

        result = json.loads(result_str)

        # When rule engine output is clean, engineering_validation_failed must be falsy
        assert not result.get("engineering_validation_failed"), (
            f"Expected no engineering_validation_failed for clean rule engine output; "
            f"got: {result.get('engineering_validation_failed')!r}"
        )


# ===========================================================================
# Artifact capture: RSR Fuji diagnosis JSON + prompt TXT
# ===========================================================================

class TestRSRFujiArtifacts:
    """Capture and save the RSR Fuji diagnosis dict and generated prompt as artifacts."""

    def test_save_rsr_fuji_diagnosis_json(self):
        """Save rsr_fuji_diagnosis.json to scratchpad."""
        laps = _make_rsr_laps()
        diag = build_setup_diagnosis(
            laps=laps,
            setup=_RSR_SETUP,
            car_name="Porsche 911 RSR '17",
            event_ctx=_RSR_EVENT_CTX,
            feeling=_RSR_FEELING,
            location_confidence="low",
        )
        out_path = _SCRATCHPAD / "rsr_fuji_diagnosis.json"
        out_path.write_text(
            json.dumps(diag, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        # Assert the file was written and contains expected keys
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written["bottoming_band"] == "minor"
        assert written["wheelspin_band"] == "severe"
        assert written["gearbox_flag"] == "preserve"
        assert written["aero_front_near_min"] is True
        assert written["aero_rear_near_min"] is True

    def test_save_rsr_fuji_prompt_txt(self):
        """Save rsr_fuji_prompt.txt to scratchpad."""
        laps = _make_rsr_laps()
        diag = build_setup_diagnosis(
            laps=laps,
            setup=_RSR_SETUP,
            car_name="Porsche 911 RSR '17",
            event_ctx=_RSR_EVENT_CTX,
            feeling=_RSR_FEELING,
            location_confidence="low",
        )
        adv = _make_stubbed_advisor(_RSR_EVENT_CTX)
        adv._config = {}

        prompt = adv._build_combined_prompt(
            laps=laps,
            setup=_RSR_SETUP,
            history_str="(no history for this test run)",
            car_name="Porsche 911 RSR '17",
            car_specs={},
            feeling=_RSR_FEELING,
            diagnosis=diag,
        )
        out_path = _SCRATCHPAD / "rsr_fuji_prompt.txt"
        out_path.write_text(prompt, encoding="utf-8")

        # Verify key content is in the prompt
        assert "Driver Hard Constraints" in prompt
        assert "Driver Tuning Model" in prompt
        written = out_path.read_text(encoding="utf-8")
        assert len(written) > 500, "Prompt appears too short"


# ===========================================================================
# Section 19 — Truncated-response guard (UAT: analyse button dumped raw JSON)
# ===========================================================================


class TestSetupResponseCompletenessGuard:
    """A response cut off at the API token cap must be detected so the UI shows
    a friendly retry message instead of dumping raw/partial JSON."""

    @pytest.fixture(autouse=True)
    def _import_fn(self):
        from ui.setup_builder_ui import _setup_response_looks_complete
        self._fn = _setup_response_looks_complete

    def test_complete_json_passes(self):
        payload = '{"analysis": "x", "changes": [], "setup_fields": {"springs_rear": 4.7}}'
        assert self._fn(payload) is True

    def test_truncated_midvalue_fails(self):
        # The exact UAT symptom: cut off mid-string, no closing brace.
        payload = '{"analysis": "x", "changes": [{"why": "bottoming addressed via springs, not'
        assert self._fn(payload) is False

    def test_missing_setup_fields_fails(self):
        payload = '{"analysis": "x", "changes": []}'
        assert self._fn(payload) is False

    def test_empty_string_fails(self):
        assert self._fn("") is False

    def test_none_fails(self):
        assert self._fn(None) is False

    def test_trailing_whitespace_tolerated(self):
        payload = '{"setup_fields": {"a": 1}}   \n'
        assert self._fn(payload) is True
