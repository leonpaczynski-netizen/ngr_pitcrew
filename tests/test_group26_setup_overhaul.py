"""
Group 26 — Setup Overhaul Acceptance Tests

Covers:
  Section A — GENERIC_DEFAULTS / resolve_ranges / save_car_ranges / _parse_setup_recommendation
  Section B — Prompt contradiction fixes (ARB, LSD, dampers, toe)
  Section C — Session objective text (race vs qualifying)
  Section D — Hybrid race context + race engineer brief
  Section E — Driver profile sections in knowledge base
  Section F — Seven-label reasoning structure / parse robustness
  Section G — Regression: named test files importable and their tests still green
                (regression run is done externally; this file validates the imports)

All tests are source-scan or in-memory only (no Qt widgets, no API calls).
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Module imports (lazy where we need monkeypatching)
# ---------------------------------------------------------------------------

from strategy.setup_ranges import (
    GENERIC_DEFAULTS,
    resolve_ranges,
    save_car_ranges,
    _load_ranges_json,
    _invalidate_cache,
)
from strategy.ai_planner import (
    _build_setup_from_scratch_prompt,
    _parse_setup_recommendation,
)
from strategy._ai_client import load_gt7_reference, clear_gt7_cache


# ---------------------------------------------------------------------------
# Minimal valid call args for _build_setup_from_scratch_prompt
# ---------------------------------------------------------------------------

_MINIMAL_KWARGS = dict(
    car="Test Car",
    track="Suzuka",
    session_type="Race",
    race_laps=10,
    min_weight_kg=0.0,
    max_power_hp=0.0,
)


def _make_prompt(**overrides) -> str:
    """Return a prompt built with minimal args + any overrides."""
    kwargs = dict(_MINIMAL_KWARGS)
    kwargs.update(overrides)
    return _build_setup_from_scratch_prompt(**kwargs)


# ---------------------------------------------------------------------------
# Minimal valid AI JSON for _parse_setup_recommendation
# ---------------------------------------------------------------------------

_MINIMAL_SETUP_JSON = json.dumps({
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
    "camber_front": -1.0,
    "camber_rear": -1.5,
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
    "shift_rpm": 7200,
    "reasoning": "Some reasoning text.",
})


# ===========================================================================
# Section A — GENERIC_DEFAULTS / resolve_ranges / save_car_ranges
# ===========================================================================

class TestSectionA_Defaults:
    """A1 — GENERIC_DEFAULTS has exactly 26 keys, each a 2-tuple with min<=max."""

    def test_defaults_have_26_keys(self):
        assert len(GENERIC_DEFAULTS) == 26, (
            f"Expected 26 keys, got {len(GENERIC_DEFAULTS)}: {sorted(GENERIC_DEFAULTS)}"
        )

    def test_all_values_are_2_tuples(self):
        for param, bounds in GENERIC_DEFAULTS.items():
            assert isinstance(bounds, tuple) and len(bounds) == 2, (
                f"{param}: expected 2-tuple, got {bounds!r}"
            )

    def test_all_min_lte_max(self):
        for param, (lo, hi) in GENERIC_DEFAULTS.items():
            assert lo <= hi, f"{param}: min ({lo}) > max ({hi})"


class TestSectionA_ResolveRangesGeneric:
    """A2 — resolve_ranges("") returns pure defaults without mutating GENERIC_DEFAULTS."""

    def test_empty_string_returns_defaults(self):
        result = resolve_ranges("")
        assert result == dict(GENERIC_DEFAULTS)

    def test_does_not_return_same_object(self):
        """Must return a copy, not the original dict."""
        result = resolve_ranges("")
        assert result is not GENERIC_DEFAULTS

    def test_repeated_calls_do_not_mutate_defaults(self):
        before = dict(GENERIC_DEFAULTS)
        for _ in range(5):
            r = resolve_ranges("")
            # Mutate the returned copy — should not affect GENERIC_DEFAULTS
            r["ride_height_front"] = (99, 99)
        assert GENERIC_DEFAULTS == before, "GENERIC_DEFAULTS was mutated by resolve_ranges"


class TestSectionA_ResolveRangesOverride:
    """A3 — resolve_ranges with a per-car override; absent car returns pure defaults."""

    def _patch_json_path(self, monkeypatch, tmp_path, data: dict):
        """Write data to a temp JSON and redirect setup_ranges._JSON_PATH to it."""
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()
        return tmp_file

    def test_partial_override_applied(self, monkeypatch, tmp_path):
        data = {"Test Car": {"ride_height_front": {"min": 70, "max": 90}}}
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Test Car")
        assert result["ride_height_front"] == (70, 90), (
            f"Expected (70, 90), got {result['ride_height_front']}"
        )

    def test_non_overridden_params_use_defaults(self, monkeypatch, tmp_path):
        data = {"Test Car": {"ride_height_front": {"min": 70, "max": 90}}}
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Test Car")
        # All other params must equal their defaults
        for param, bounds in GENERIC_DEFAULTS.items():
            if param != "ride_height_front":
                assert result[param] == bounds, (
                    f"{param}: expected {bounds}, got {result[param]}"
                )

    def test_absent_car_returns_pure_defaults(self, monkeypatch, tmp_path):
        data = {"Some Other Car": {"ride_height_front": {"min": 70, "max": 90}}}
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Unknown Car XYZ")
        assert result == dict(GENERIC_DEFAULTS)

    def test_whitespace_stripped_from_car_name(self, monkeypatch, tmp_path):
        data = {"My Car": {"ride_height_rear": {"min": 75, "max": 95}}}
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("  My Car  ")
        assert result["ride_height_rear"] == (75, 95)


class TestSectionA_SaveCarRanges:
    """A4 — save_car_ranges raises ValueError when min>max."""

    def test_raises_value_error_when_min_gt_max(self, tmp_path, monkeypatch):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()

        with pytest.raises(ValueError, match="min.*max|max.*min"):
            save_car_ranges("Test Car", {"ride_height_front": {"min": 200, "max": 100}})

    def test_valid_save_does_not_raise(self, tmp_path, monkeypatch):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()

        # Should not raise
        save_car_ranges("Test Car", {"ride_height_front": {"min": 60, "max": 120}})
        data = json.loads(tmp_file.read_text(encoding="utf-8"))
        assert data["Test Car"]["ride_height_front"] == {"min": 60, "max": 120}

    def test_raises_when_min_equals_max_plus_one(self, tmp_path, monkeypatch):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()

        with pytest.raises(ValueError):
            save_car_ranges("Test Car", {"springs_front": {"min": 10.0, "max": 9.0}})


class TestSectionA_ParseSetupRecommendationClamping:
    """A5 & A6 — _parse_setup_recommendation clamps params via ranges."""

    def test_aero_front_clamped_to_range_min(self):
        """aero_front=350 with ranges aero_front=(700,900) -> 700."""
        ranges_override = dict(GENERIC_DEFAULTS)
        ranges_override["aero_front"] = (700, 900)

        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "aero_front": 350,
        })
        result = _parse_setup_recommendation(raw, ranges=ranges_override)
        assert result.aero_front == 700, (
            f"Expected aero_front clamped to 700, got {result.aero_front}"
        )

    def test_ride_height_rear_clamped_to_range_min(self):
        """ride_height_rear=65 with ranges ride_height_rear=(70,120) -> 70."""
        ranges_override = dict(GENERIC_DEFAULTS)
        ranges_override["ride_height_rear"] = (70, 120)

        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "ride_height_rear": 65,
        })
        result = _parse_setup_recommendation(raw, ranges=ranges_override)
        assert result.ride_height_rear == 70, (
            f"Expected ride_height_rear clamped to 70, got {result.ride_height_rear}"
        )

    def test_parse_with_ranges_none_uses_generic_defaults(self):
        """ranges=None must fall back to generic defaults without raising."""
        result = _parse_setup_recommendation(_MINIMAL_SETUP_JSON, ranges=None)
        # Just confirm it doesn't raise and returns a reasonable value
        assert result.ride_height_front == 80

    def test_aero_floor_zero_reachable(self):
        """Generic aero min is 0 — a value of 0 should NOT be clamped upward."""
        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "aero_front": 0,
            "aero_rear": 0,
        })
        result = _parse_setup_recommendation(raw, ranges=dict(GENERIC_DEFAULTS))
        assert result.aero_front == 0
        assert result.aero_rear == 0

    def test_generic_defaults_aero_min_is_zero(self):
        """A6 — confirm the generic aero_front min is 0."""
        assert GENERIC_DEFAULTS["aero_front"][0] == 0
        assert GENERIC_DEFAULTS["aero_rear"][0] == 0


# ===========================================================================
# Section B — Prompt contradiction fixes
# ===========================================================================

class TestSectionB_ARBRange:
    """B1 — ARB stated as 1-7; '1-10' or '1–10' must NOT appear."""

    def test_arb_range_1_to_7_present(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        # The ranges block will contain "1–7" (with en-dash) from _fmt_range
        assert "1–7" in prompt, f"ARB 1-7 range not found in prompt"

    def test_arb_not_1_to_10(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        # The ARB line should say "1–7" (or "1-7"), not "1–10" / "1-10".
        # Search specifically in the ARB line context to avoid false matches
        # from damper range "1–100" (which contains "1–10" as a substring).
        import re as _re
        # Find every line that mentions arb_front or arb_rear
        arb_lines = [ln for ln in prompt.splitlines()
                     if "arb_front" in ln.lower() or "arb_rear" in ln.lower()]
        assert arb_lines, "No ARB line found in prompt"
        for ln in arb_lines:
            # A range "1–10" only (not "1–100") would end with "10" not "100"
            # Use regex to detect stand-alone 1-10 or 1–10 that is NOT 1-100/1–100
            assert not _re.search(r"1[-–]10(?!\d)", ln), (
                f"Forbidden ARB range '1-10' or '1–10' found in ARB line: {ln!r}"
            )


class TestSectionB_LSDRange:
    """B2 — LSD stated as 0-60; 'min 5' must NOT appear."""

    def test_lsd_range_0_to_60_present(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        assert "0–60" in prompt, "LSD 0–60 range not found in prompt"

    def test_lsd_no_min_5(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        assert "min 5" not in prompt.lower(), "'min 5' constraint should not appear in prompt"


class TestSectionB_DamperGuideline:
    """B3 — damper 'typical 30' is absent OR has 'guideline'/'not a constraint' qualifier."""

    def test_typical_30_absent_or_qualified(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        # Check every occurrence of "typical 30" (the old unqualified damper guideline).
        # If the phrase exists it MUST be accompanied by a qualifier within the same line.
        import re as _re
        for ln in prompt.splitlines():
            if "typical" in ln.lower() and "30" in ln:
                has_qualifier = ("guideline" in ln.lower() or
                                 "not a constraint" in ln.lower())
                assert has_qualifier, (
                    f"'typical 30' found in damper line without "
                    f"'guideline'/'not a constraint' qualifier:\n  {ln!r}"
                )


class TestSectionB_ToeConvention:
    """B4 — toe convention: 'toe-out' appears; negative-front/positive-rear stated."""

    def test_toe_out_appears(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        assert "toe-out" in prompt.lower(), "'toe-out' not found in prompt"

    def test_toe_convention_negative_front(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        # Convention text: negative front = toe-out
        assert "negative" in prompt.lower(), "toe convention 'negative' direction not stated"

    def test_toe_convention_positive_rear(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        assert "positive" in prompt.lower(), "toe convention 'positive' direction not stated"


# ===========================================================================
# Section C — Session objective text
# ===========================================================================

class TestSectionC_ObjectiveText:
    """C1-C3 — 'lowest total race time' for race sessions; quali unchanged."""

    def test_timed_race_contains_lowest_total_race_time(self):
        prompt = _make_prompt(session_type="Race", race_type="timed")
        assert "lowest total race time" in prompt, (
            "'lowest total race time' not found in timed race prompt"
        )

    def test_timed_race_not_old_objective(self):
        prompt = _make_prompt(session_type="Race", race_type="timed")
        assert "optimise for consistency, tyre life, fuel efficiency" not in prompt, (
            "Old objective text found in timed race prompt"
        )

    def test_lap_race_contains_lowest_total_race_time(self):
        prompt = _make_prompt(session_type="Race", race_type="lap", race_laps=20)
        assert "lowest total race time" in prompt, (
            "'lowest total race time' not found in lap race prompt"
        )

    def test_lap_race_not_old_objective(self):
        prompt = _make_prompt(session_type="Race", race_type="lap", race_laps=20)
        assert "optimise for consistency, tyre life, fuel efficiency" not in prompt

    def test_qualifying_contains_1_qualifying_lap(self):
        prompt = _make_prompt(session_type="Qualifying", race_type="lap")
        assert "1 qualifying lap" in prompt, (
            "'1 qualifying lap' not found in qualifying prompt"
        )

    def test_qualifying_not_lowest_total_race_time(self):
        prompt = _make_prompt(session_type="Qualifying", race_type="lap")
        assert "lowest total race time" not in prompt, (
            "'lowest total race time' must NOT appear in qualifying prompt"
        )


# ===========================================================================
# Section D — Hybrid race context + race engineer brief
# ===========================================================================

class TestSectionD_HybridBlock:
    """D1 — duration_mins and mandatory_stops appear in labelled lines when non-zero."""

    def test_duration_and_stops_present_when_non_zero(self):
        prompt = _make_prompt(
            session_type="Race", race_type="timed",
            duration_mins=50, mandatory_stops=2,
        )
        assert "50" in prompt, "duration_mins=50 not found in prompt"
        assert "2" in prompt, "mandatory_stops=2 not found in prompt"

    def test_duration_line_label_present(self):
        prompt = _make_prompt(
            session_type="Race", race_type="timed",
            duration_mins=50, mandatory_stops=0,
        )
        # The labelled line must say "Race duration: 50"
        assert "Race duration: 50" in prompt, (
            "Labelled 'Race duration: 50' line not found in prompt"
        )

    def test_mandatory_stops_line_label_present(self):
        prompt = _make_prompt(
            session_type="Race", race_type="timed",
            duration_mins=50, mandatory_stops=2,
        )
        assert "Mandatory pit stops: 2" in prompt, (
            "Labelled 'Mandatory pit stops: 2' line not found in prompt"
        )

    def test_zero_duration_not_in_prompt(self):
        """With all zeros, no 'Race duration: 0' line should appear."""
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            duration_mins=0, mandatory_stops=0,
        )
        assert "Race duration: 0" not in prompt, (
            "'Race duration: 0' must not appear when duration_mins=0"
        )

    def test_zero_stops_not_in_prompt(self):
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            duration_mins=0, mandatory_stops=0,
        )
        assert "Mandatory pit stops: 0" not in prompt, (
            "'Mandatory pit stops: 0' must not appear when mandatory_stops=0"
        )


class TestSectionD_RaceEngineerBrief:
    """D2 & D3 — race_engineer_brief appears verbatim; empty brief omits heading."""

    def test_non_empty_brief_appears_verbatim(self):
        brief = "Push hard on lap 3; preserve tyres after that."
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief=brief,
        )
        assert brief in prompt, (
            "race_engineer_brief not found verbatim in prompt"
        )

    def test_non_empty_brief_under_heading(self):
        brief = "Push hard on lap 3; preserve tyres after that."
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief=brief,
        )
        heading_idx = prompt.find("## Race Engineer Brief")
        assert heading_idx != -1, "'## Race Engineer Brief' heading not in prompt"
        brief_idx = prompt.find(brief)
        assert brief_idx > heading_idx, "Brief appears before the heading"

    def test_empty_brief_omits_heading(self):
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief="",
        )
        assert "## Race Engineer Brief" not in prompt, (
            "'## Race Engineer Brief' heading must not appear when brief is empty"
        )

    def test_whitespace_only_brief_omits_heading(self):
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief="   \n  ",
        )
        assert "## Race Engineer Brief" not in prompt, (
            "'## Race Engineer Brief' heading must not appear for whitespace-only brief"
        )

    def test_brief_with_quotes_and_backslashes_builds_without_exception(self):
        brief = 'Use "full attack" mode; lap\\ntarget: 1:30.'
        # Must not raise
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief=brief,
        )
        assert brief in prompt

    def test_brief_with_newlines_builds_without_exception(self):
        brief = "Line 1\nLine 2\nLine 3 — pit lap 8."
        prompt = _make_prompt(
            session_type="Race", race_type="lap",
            race_engineer_brief=brief,
        )
        # Brief is stripped; individual lines should appear
        assert "Line 1" in prompt
        assert "Line 3" in prompt


# ===========================================================================
# Section E — Driver profile sections in knowledge base
# ===========================================================================

class TestSectionE_DriverProfile:
    """E — load_gt7_reference() contains the new Part 2 sections."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        """Clear the GT7 ref cache before each test."""
        clear_gt7_cache()
        yield
        clear_gt7_cache()

    def test_driver_race_behaviour_section_present(self):
        ref = load_gt7_reference()
        assert "### Driver Race Behaviour" in ref, (
            "'### Driver Race Behaviour' not found in gt7_tuning_reference.md"
        )

    def test_tyre_wear_priorities_section_present(self):
        ref = load_gt7_reference()
        assert "### Tyre-Wear Priorities" in ref, (
            "'### Tyre-Wear Priorities' not found in gt7_tuning_reference.md"
        )

    def test_fuel_save_if_instructed_bullet_present(self):
        ref = load_gt7_reference()
        assert "fuel-save if instructed" in ref, (
            "Representative bullet 'fuel-save if instructed' not found in knowledge base"
        )

    def test_front_left_bullet_present(self):
        ref = load_gt7_reference()
        assert "front-left" in ref, (
            "Representative bullet 'front-left' (tyre-wear priority) not found in knowledge base"
        )


# ===========================================================================
# Section F — Seven-label reasoning structure
# ===========================================================================

_SEVEN_LABELS = [
    "Expected lap-time effect",
    "Expected tyre-wear effect",
    "Expected fuel effect",
    "Expected braking-stability effect",
    "Confidence",
    "Validation method",
    "Telemetry indicator",
]


class TestSectionF_SevenLabels:
    """F1 — race prompt contains all seven reasoning labels."""

    def test_all_seven_labels_in_race_prompt(self):
        prompt = _make_prompt(session_type="Race", race_type="lap")
        missing = [label for label in _SEVEN_LABELS if label not in prompt]
        assert not missing, (
            f"Missing seven-label reasoning entries in prompt: {missing}"
        )

    def test_all_seven_labels_in_timed_race_prompt(self):
        prompt = _make_prompt(session_type="Race", race_type="timed", duration_mins=60)
        missing = [label for label in _SEVEN_LABELS if label not in prompt]
        assert not missing, (
            f"Missing seven-label reasoning entries in timed race prompt: {missing}"
        )


class TestSectionF_ParseReasoningRobustness:
    """F2 — _parse_setup_recommendation handles both old and new reasoning formats."""

    def test_plain_paragraph_reasoning_does_not_raise(self):
        """Old-format: plain prose in the reasoning field."""
        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "reasoning": "Springs set stiff to reduce body roll. Balanced setup overall.",
        })
        result = _parse_setup_recommendation(raw, ranges=None)
        assert "Springs set stiff" in result.reasoning

    def test_new_seven_label_reasoning_does_not_raise(self):
        """New-format: seven labelled sub-points per change block."""
        new_reasoning = (
            "springs_front set to 3.50\n"
            "Expected lap-time effect: reduces body roll\n"
            "Expected tyre-wear effect: neutral\n"
            "Expected fuel effect: neutral\n"
            "Expected braking-stability effect: improves stability\n"
            "Confidence: medium\n"
            "Validation method: run 3 laps\n"
            "Telemetry indicator: suspension travel\n"
        )
        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "reasoning": new_reasoning,
        })
        result = _parse_setup_recommendation(raw, ranges=None)
        assert "Expected lap-time effect" in result.reasoning

    def test_empty_reasoning_field_does_not_raise(self):
        raw = json.dumps({**json.loads(_MINIMAL_SETUP_JSON), "reasoning": ""})
        result = _parse_setup_recommendation(raw, ranges=None)
        assert result.reasoning == ""

    def test_missing_reasoning_field_does_not_raise(self):
        d = json.loads(_MINIMAL_SETUP_JSON)
        del d["reasoning"]
        result = _parse_setup_recommendation(json.dumps(d), ranges=None)
        assert isinstance(result.reasoning, str)


# ===========================================================================
# Section G — Source-level regression guards
# (These confirm the named regression files are importable and that the
#  key functions/classes referenced by those tests still exist in the source.
#  The actual pytest run of those files is done externally.)
# ===========================================================================

class TestSectionG_RegressionImports:
    """G — named regression test modules are importable."""

    def test_garage_completion_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_garage_completion")
        assert mod is not None

    def test_group17h_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group17h_track_context_prompt")
        assert mod is not None

    def test_group17n_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group17n_uat_defects")
        assert mod is not None

    def test_group15_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group15_ai_context_fixes")
        assert mod is not None

    def test_group10_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group10_ai_prompt_bop")
        assert mod is not None

    def test_group25_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group25_setup_builder_extraction")
        assert mod is not None


class TestSectionG_SourceGuards:
    """G — production symbols still present as expected by regression test files."""

    def test_session_db_has_get_tracks_for_car_recommendations(self):
        from data.session_db import SessionDB
        assert hasattr(SessionDB, "get_tracks_for_car_recommendations")

    def test_session_db_has_get_setup_history_for_car_track(self):
        from data.session_db import SessionDB
        assert hasattr(SessionDB, "get_setup_history_for_car_track")

    def test_ai_planner_has_build_car_setup(self):
        from strategy.ai_planner import build_car_setup
        assert callable(build_car_setup)

    def test_setup_builder_ui_no_init(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "def __init__" not in src, (
            "setup_builder_ui.py must NOT define __init__ (breaks mixin pattern)"
        )

    def test_setup_builder_ui_has_rebound_setup_spinboxes(self):
        src = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
        assert "def _rebound_setup_spinboxes" in src

    def test_dashboard_has_setup_result_queue_attr(self):
        src = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
        assert "self._setup_result_queue" in src

    def test_car_ranges_dialog_importable(self):
        """ui/car_ranges_dialog.py must exist and be importable (no Qt needed for import)."""
        car_ranges_path = ROOT / "ui" / "car_ranges_dialog.py"
        assert car_ranges_path.exists(), "ui/car_ranges_dialog.py not found"
