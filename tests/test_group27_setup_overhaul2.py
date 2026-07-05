"""
Group 27 — Setup Overhaul 2 Acceptance Tests

Covers:
  Story 1 — build_car_setup: max_tokens=6000, _is_truncated, retry logic,
             double-failure RuntimeError with correct message.
  Story 2 — Camber positive 0–6: GENERIC_DEFAULTS, resolve_ranges normalisation,
             _parse_setup_recommendation clamping, prompt text, JSON data file.
  Story 3 — Displayed AI suggestions respect ranges: _display_setup_result
             source-scan for _last_setup_ai_fields usage and "(clamped to" annotation.
  Story 4 — Highlight on apply, clear on save: method existence, call patterns.

All tests are source-scan or in-memory only (no Qt widgets, no real API calls).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------------------
# Module imports
# ---------------------------------------------------------------------------

from strategy.setup_ranges import (
    GENERIC_DEFAULTS,
    resolve_ranges,
    _invalidate_cache,
)
from strategy.ai_planner import (
    _is_truncated,
    _parse_setup_recommendation,
    _build_setup_from_scratch_prompt,
)

# ---------------------------------------------------------------------------
# Minimal valid AI JSON reused across parse tests
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

# Minimal args needed by build_car_setup
_BUILD_KWARGS = dict(
    car="Test Car",
    track="Suzuka",
    session_type="Race",
    race_laps=10,
    min_weight_kg=0.0,
    max_power_hp=0.0,
    api_key="fake-key",
)

# ---------------------------------------------------------------------------
# Helper: load setup_builder_ui.py source text without importing (avoids Qt)
# ---------------------------------------------------------------------------

# Setup builder UI now spans two files: the mixin and the extracted form widget.
# Source-scan tests search the combined text to preserve coverage after refactor.
_SETUP_BUILDER_SRC = (
    (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")
    + "\n"
    + (ROOT / "ui" / "setup_form_widget.py").read_text(encoding="utf-8")
)
_AI_PLANNER_SRC    = (ROOT / "strategy" / "ai_planner.py").read_text(encoding="utf-8")


# ===========================================================================
# Story 1 — build_car_setup: resilience to truncated / malformed AI responses
# ===========================================================================

class TestStory1_MaxTokens:
    """AC1 — build_car_setup uses max_tokens=6000, not 2500."""

    def test_max_tokens_6000_in_source(self):
        """Source must contain max_tokens=6000 in the build_car_setup context."""
        # _api_kwargs dict contains max_tokens=6000 inside build_car_setup
        assert "max_tokens=6000" in _AI_PLANNER_SRC, (
            "build_car_setup must set max_tokens=6000 (was 2500 before this story)"
        )

    def test_max_tokens_2500_not_in_build_setup(self):
        """The old value 2500 must not appear as the token limit in build_car_setup."""
        # Verify 2500 is not present anywhere in build_car_setup context.
        # We check the whole file: if 2500 was left as a hardcoded token limit, this fails.
        assert "max_tokens=2500" not in _AI_PLANNER_SRC, (
            "Old max_tokens=2500 still present — should have been raised to 6000"
        )


class TestStory1_IsTruncated:
    """AC2 — _is_truncated(raw) logic."""

    def test_open_brace_is_truncated(self):
        assert _is_truncated('{"a":1') is True

    def test_closed_brace_not_truncated(self):
        assert _is_truncated('{"a":1}') is False

    def test_trailing_whitespace_not_truncated(self):
        """A valid JSON ending with } plus trailing whitespace must NOT be truncated."""
        assert _is_truncated('{"a":1}   \n  ') is False

    def test_trailing_whitespace_truncated(self):
        """Incomplete JSON with trailing whitespace is still truncated."""
        assert _is_truncated('{"a":1  \n  ') is True

    def test_empty_string_is_truncated(self):
        assert _is_truncated('') is True

    def test_only_whitespace_is_truncated(self):
        assert _is_truncated('   \n ') is True


class TestStory1_RetrySuccess:
    """AC3 — first call returns bad JSON, second returns valid → returns CarSetupRecommendation."""

    def test_retry_on_json_decode_error_returns_result(self):
        """Mock call_api: first call returns malformed JSON, second returns valid JSON.

        build_car_setup should retry once and return a CarSetupRecommendation.
        """
        from strategy.ai_planner import build_car_setup, CarSetupRecommendation

        call_count = {"n": 0}

        def fake_call_api(prompt, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "not valid json at all"
            return _MINIMAL_SETUP_JSON

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            result = build_car_setup(**_BUILD_KWARGS)

        assert isinstance(result, CarSetupRecommendation), (
            f"Expected CarSetupRecommendation, got {type(result)}"
        )
        assert call_count["n"] == 2, (
            f"Expected exactly 2 API calls (first failed, second succeeded), got {call_count['n']}"
        )

    def test_retry_on_truncation_returns_result(self):
        """Mock call_api: first returns truncated JSON (no closing }), second is valid."""
        from strategy.ai_planner import build_car_setup, CarSetupRecommendation

        call_count = {"n": 0}

        def fake_call_api(prompt, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Truncated — does not end with }
                return _MINIMAL_SETUP_JSON.rstrip("}").rstrip()
            return _MINIMAL_SETUP_JSON

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            result = build_car_setup(**_BUILD_KWARGS)

        assert isinstance(result, CarSetupRecommendation)
        assert call_count["n"] == 2


class TestStory1_DoubleFaultRuntimeError:
    """AC4 — both calls return bad JSON → RuntimeError with correct message."""

    def test_double_invalid_json_raises_runtime_error(self):
        """Both calls return invalid JSON → RuntimeError with correct message."""
        from strategy.ai_planner import build_car_setup

        def fake_call_api(prompt, **kwargs):
            return "invalid json {{"

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            with pytest.raises(RuntimeError) as exc_info:
                build_car_setup(**_BUILD_KWARGS)

        msg = str(exc_info.value)
        assert "Setup could not be generated" in msg, (
            f"RuntimeError message must contain 'Setup could not be generated', got: {msg!r}"
        )

    def test_double_truncated_raises_runtime_error(self):
        """Both calls return truncated JSON → RuntimeError with correct message."""
        from strategy.ai_planner import build_car_setup

        truncated = _MINIMAL_SETUP_JSON.rstrip("}").rstrip()

        def fake_call_api(prompt, **kwargs):
            return truncated

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            with pytest.raises(RuntimeError) as exc_info:
                build_car_setup(**_BUILD_KWARGS)

        msg = str(exc_info.value)
        assert "Setup could not be generated" in msg, (
            f"RuntimeError message must contain 'Setup could not be generated', got: {msg!r}"
        )

    def test_error_message_does_not_contain_raw_json(self):
        """RuntimeError message must not leak raw JSON or traceback detail."""
        from strategy.ai_planner import build_car_setup

        leaky_json = '{"ride_height_front": 80, "unclosed": '

        def fake_call_api(prompt, **kwargs):
            return leaky_json

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            with pytest.raises(RuntimeError) as exc_info:
                build_car_setup(**_BUILD_KWARGS)

        msg = str(exc_info.value)
        # The raw JSON snippet must not appear verbatim in the user-visible message
        assert "ride_height_front" not in msg, (
            "RuntimeError message must not contain raw JSON field names"
        )
        assert "unclosed" not in msg, (
            "RuntimeError message must not contain raw JSON content"
        )


# ===========================================================================
# Story 2 — Camber positive 0–6 everywhere
# ===========================================================================

class TestStory2_GenericDefaultsCamber:
    """AC5 — GENERIC_DEFAULTS camber_front and camber_rear == (0.0, 6.0)."""

    def test_camber_front_default_is_0_to_6(self):
        assert GENERIC_DEFAULTS["camber_front"] == (0.0, 6.0), (
            f"camber_front default expected (0.0, 6.0), got {GENERIC_DEFAULTS['camber_front']}"
        )

    def test_camber_rear_default_is_0_to_6(self):
        assert GENERIC_DEFAULTS["camber_rear"] == (0.0, 6.0), (
            f"camber_rear default expected (0.0, 6.0), got {GENERIC_DEFAULTS['camber_rear']}"
        )

    def test_camber_front_min_is_non_negative(self):
        lo, hi = GENERIC_DEFAULTS["camber_front"]
        assert lo >= 0, f"camber_front min must be >= 0, got {lo}"

    def test_camber_rear_min_is_non_negative(self):
        lo, hi = GENERIC_DEFAULTS["camber_rear"]
        assert lo >= 0, f"camber_rear min must be >= 0, got {lo}"


class TestStory2_ResolveRangesNormalisesNegativeCamber:
    """AC6 — resolve_ranges normalises negative per-car camber to positive convention."""

    def _patch_json_path(self, monkeypatch, tmp_path, data: dict):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()
        return tmp_file

    def test_negative_camber_min_max_normalised(self, monkeypatch, tmp_path):
        """Car with camber_front min=-3.0, max=0.0 → resolve_ranges returns (0.0, 3.0)."""
        data = {
            "Legacy Car": {
                "camber_front": {"min": -3.0, "max": 0.0},
            }
        }
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Legacy Car")
        lo, hi = result["camber_front"]
        assert lo >= 0 and hi >= 0, (
            f"camber_front bounds must be non-negative after normalisation, got ({lo}, {hi})"
        )
        assert lo <= hi, (
            f"camber_front lo must be <= hi after normalisation, got ({lo}, {hi})"
        )
        assert (lo, hi) == (0.0, 3.0), (
            f"camber_front (-3.0, 0.0) should normalise to (0.0, 3.0), got ({lo}, {hi})"
        )

    def test_negative_camber_both_negative_normalised(self, monkeypatch, tmp_path):
        """Car with camber_rear min=-4.0, max=-1.0 → resolve_ranges returns (1.0, 4.0)."""
        data = {
            "Legacy Car": {
                "camber_rear": {"min": -4.0, "max": -1.0},
            }
        }
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Legacy Car")
        lo, hi = result["camber_rear"]
        assert lo >= 0 and hi >= 0, (
            f"camber_rear bounds must be non-negative after normalisation, got ({lo}, {hi})"
        )
        assert lo <= hi, (
            f"camber_rear lo must be <= hi after normalisation, got ({lo}, {hi})"
        )
        assert (lo, hi) == (1.0, 4.0), (
            f"camber_rear (-4.0, -1.0) should normalise to (1.0, 4.0), got ({lo}, {hi})"
        )

    def test_already_positive_camber_unchanged(self, monkeypatch, tmp_path):
        """Car with already-positive camber range is not mutated."""
        data = {
            "Modern Car": {
                "camber_front": {"min": 0.5, "max": 4.5},
            }
        }
        self._patch_json_path(monkeypatch, tmp_path, data)

        result = resolve_ranges("Modern Car")
        assert result["camber_front"] == (0.5, 4.5), (
            f"Positive camber range should be unchanged, got {result['camber_front']}"
        )


class TestStory2_ParseSetupCamberClamping:
    """AC7 — _parse_setup_recommendation clamps negative camber to 0.0 and uses positive defaults."""

    def test_negative_camber_front_clamped_to_zero(self):
        """camber_front=-2.5 with positive ranges (0.0, 6.0) → clamped to 0.0."""
        ranges = dict(GENERIC_DEFAULTS)
        # GENERIC_DEFAULTS has camber_front=(0.0,6.0) — negative input must clamp to 0
        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "camber_front": -2.5,
        })
        result = _parse_setup_recommendation(raw, ranges=ranges)
        assert result.camber_front == 0.0, (
            f"camber_front=-2.5 with range (0.0,6.0) must clamp to 0.0, got {result.camber_front}"
        )

    def test_negative_camber_rear_clamped_to_zero(self):
        """camber_rear=-1.5 with positive ranges (0.0, 6.0) → clamped to 0.0."""
        ranges = dict(GENERIC_DEFAULTS)
        raw = json.dumps({
            **json.loads(_MINIMAL_SETUP_JSON),
            "camber_rear": -1.5,
        })
        result = _parse_setup_recommendation(raw, ranges=ranges)
        assert result.camber_rear == 0.0, (
            f"camber_rear=-1.5 with range (0.0,6.0) must clamp to 0.0, got {result.camber_rear}"
        )

    def test_camber_default_front_is_positive(self):
        """When camber_front is omitted, default is 1.0 (positive)."""
        d = json.loads(_MINIMAL_SETUP_JSON)
        del d["camber_front"]
        result = _parse_setup_recommendation(json.dumps(d), ranges=dict(GENERIC_DEFAULTS))
        assert result.camber_front >= 0.0, (
            f"Omitted camber_front default must be >= 0.0, got {result.camber_front}"
        )
        assert result.camber_front == 1.0, (
            f"Omitted camber_front default must be 1.0 (positive convention), got {result.camber_front}"
        )

    def test_camber_default_rear_is_positive(self):
        """When camber_rear is omitted, default is 1.5 (positive)."""
        d = json.loads(_MINIMAL_SETUP_JSON)
        del d["camber_rear"]
        result = _parse_setup_recommendation(json.dumps(d), ranges=dict(GENERIC_DEFAULTS))
        assert result.camber_rear >= 0.0, (
            f"Omitted camber_rear default must be >= 0.0, got {result.camber_rear}"
        )
        assert result.camber_rear == 1.5, (
            f"Omitted camber_rear default must be 1.5 (positive convention), got {result.camber_rear}"
        )


class TestStory2_PromptCamberPositive:
    """AC8 — _build_setup_from_scratch_prompt contains 'always POSITIVE' and not 'always negative'."""

    def _make_prompt(self, **overrides) -> str:
        kwargs = dict(
            car="Test Car",
            track="Suzuka",
            session_type="Race",
            race_laps=10,
            min_weight_kg=0.0,
            max_power_hp=0.0,
        )
        kwargs.update(overrides)
        return _build_setup_from_scratch_prompt(**kwargs)

    def test_always_positive_in_prompt(self):
        prompt = self._make_prompt()
        assert "always POSITIVE" in prompt, (
            "Prompt must contain 'always POSITIVE' for camber convention"
        )

    def test_always_negative_not_in_prompt(self):
        prompt = self._make_prompt()
        assert "always negative" not in prompt.lower(), (
            "Prompt must not contain 'always negative' — camber convention is now positive"
        )


class TestStory2_CarSetupRangesJson:
    """AC9 — data/car_setup_ranges.json: all cars' camber_front/camber_rear bounds are >= 0."""

    def test_all_camber_values_non_negative(self):
        json_path = ROOT / "data" / "car_setup_ranges.json"
        assert json_path.exists(), f"car_setup_ranges.json not found at {json_path}"

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), "car_setup_ranges.json must contain a JSON object"

        failures = []
        for car_name, car_data in data.items():
            if not isinstance(car_data, dict):
                continue
            for param in ("camber_front", "camber_rear"):
                bounds = car_data.get(param)
                if bounds is None:
                    continue
                lo = bounds.get("min")
                hi = bounds.get("max")
                if lo is not None and lo < 0:
                    failures.append(
                        f"{car_name}.{param}.min = {lo} (must be >= 0)"
                    )
                if hi is not None and hi < 0:
                    failures.append(
                        f"{car_name}.{param}.max = {hi} (must be >= 0)"
                    )

        assert not failures, (
            "Negative camber bounds found in car_setup_ranges.json:\n"
            + "\n".join(failures)
        )


# ===========================================================================
# Story 3 — Displayed AI suggestions respect ranges (source-scan)
# ===========================================================================

class TestStory3_DisplaySetupResult:
    """AC10 — _display_setup_result uses _last_setup_ai_fields and has '(clamped to' annotation."""

    def test_display_result_references_last_setup_ai_fields(self):
        """_display_setup_result must build change rows from self._last_setup_ai_fields."""
        assert "_last_setup_ai_fields" in _SETUP_BUILDER_SRC, (
            "setup_builder_ui.py must contain _last_setup_ai_fields"
        )

    def test_display_result_has_clamped_to_annotation(self):
        """_display_setup_result must output '(clamped to' text for out-of-range AI values."""
        assert "(clamped to" in _SETUP_BUILDER_SRC, (
            "setup_builder_ui.py must contain '(clamped to' annotation in display logic"
        )

    def test_display_result_method_exists(self):
        """_display_setup_result method must exist in SetupBuilderMixin."""
        assert "def _display_setup_result" in _SETUP_BUILDER_SRC, (
            "setup_builder_ui.py must define _display_setup_result"
        )

    def test_display_result_uses_clamped_val_from_ai_fields(self):
        """The display function reads clamped val from _last_setup_ai_fields when building rows.

        Source-scan: the variable _clamped_val is set from the matched pair in
        _last_setup_ai_fields, and used in the change row output.
        """
        assert "_clamped_val" in _SETUP_BUILDER_SRC, (
            "_display_setup_result must use a _clamped_val variable derived from _last_setup_ai_fields"
        )


# ===========================================================================
# Story 4 — Highlight on apply, clear on save
# ===========================================================================

class TestStory4_MethodExistence:
    """AC11 — _highlight_changed_fields and _clear_setup_highlights exist on the mixin."""

    def test_highlight_changed_fields_method_exists(self):
        assert "def _highlight_changed_fields" in _SETUP_BUILDER_SRC, (
            "SetupBuilderMixin must define _highlight_changed_fields"
        )

    def test_clear_setup_highlights_method_exists(self):
        assert "def _clear_setup_highlights" in _SETUP_BUILDER_SRC, (
            "SetupBuilderMixin must define _clear_setup_highlights"
        )


class TestStory4_SetupSaveClearsHighlights:
    """AC12 — _setup_save calls _clear_setup_highlights."""

    def test_setup_save_calls_clear_highlights(self):
        """Find _setup_save method body and verify it calls _clear_setup_highlights."""
        # Extract the body of _setup_save by finding its definition
        src = _SETUP_BUILDER_SRC
        method_start = src.find("def _setup_save(")
        assert method_start != -1, "def _setup_save not found in setup_builder_ui.py"

        # Find the next method definition after _setup_save (at same indentation)
        # to bound the search to _setup_save's body only.
        next_method = src.find("\n    def ", method_start + 1)
        method_body = src[method_start:next_method] if next_method != -1 else src[method_start:]

        assert "_clear_setup_highlights" in method_body, (
            "_setup_save must call _clear_setup_highlights but it does not"
        )


class TestStory4_ApplyAndSaveAiSetup:
    """AC13 — _apply_and_save_ai_setup does NOT call _setup_save AND calls _highlight_changed_fields."""

    def _get_method_body(self, method_name: str) -> str:
        src = _SETUP_BUILDER_SRC
        start = src.find(f"def {method_name}(")
        assert start != -1, f"def {method_name} not found in setup_builder_ui.py"
        next_method = src.find("\n    def ", start + 1)
        return src[start:next_method] if next_method != -1 else src[start:]

    def test_apply_and_save_does_not_call_setup_save(self):
        body = self._get_method_body("_apply_and_save_ai_setup")
        assert "_setup_save" not in body, (
            "_apply_and_save_ai_setup must NOT call _setup_save "
            "(auto-save was removed — user must click Save Setup)"
        )

    def test_apply_and_save_calls_highlight_changed_fields(self):
        body = self._get_method_body("_apply_and_save_ai_setup")
        assert "_highlight_changed_fields" in body, (
            "_apply_and_save_ai_setup must call _highlight_changed_fields"
        )


class TestStory4_ButtonLabel:
    """AC14 — button label is 'Apply Pit Crew recommendation' (updated by AC24/Group 42),
    NOT 'Apply to Setup & Save'."""

    def test_apply_to_setup_label_present(self):
        # AC24 (Group 42) renamed the label to "Apply Pit Crew recommendation".
        # Accept either the old label (pre-G42) or the new one so the assertion
        # remains meaningful across both forms of the source.
        has_old = '"Apply to Setup"' in _SETUP_BUILDER_SRC or "'Apply to Setup'" in _SETUP_BUILDER_SRC
        has_new = "Apply Pit Crew recommendation" in _SETUP_BUILDER_SRC
        assert has_old or has_new, (
            "setup_builder_ui.py / setup_form_widget.py must contain the Apply button label "
            "('Apply to Setup' pre-G42 or 'Apply Pit Crew recommendation' post-G42)"
        )

    def test_apply_to_setup_and_save_label_absent(self):
        assert "Apply to Setup & Save" not in _SETUP_BUILDER_SRC, (
            "Old button label 'Apply to Setup & Save' must not appear in setup_builder_ui.py "
            "(auto-save was removed)"
        )


class TestStory4_ApplyBuildSetupResultHighlights:
    """AC15 — _apply_build_setup_result calls _highlight_changed_fields."""

    def test_apply_build_setup_result_calls_highlight(self):
        src = _SETUP_BUILDER_SRC
        method_start = src.find("def _apply_build_setup_result(")
        assert method_start != -1, "def _apply_build_setup_result not found"

        next_method = src.find("\n    def ", method_start + 1)
        body = src[method_start:next_method] if next_method != -1 else src[method_start:]

        assert "_highlight_changed_fields" in body, (
            "_apply_build_setup_result must call _highlight_changed_fields"
        )


# ===========================================================================
# Fix A — Deterministic analyse-path change contract (strategy/driving_advisor.py)
# ===========================================================================

# Load source text for source-scan helpers
_DRIVING_ADVISOR_SRC = (ROOT / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")


class TestFixA_ResolveFieldKey:
    """FIX A AC1 — _resolve_field_key resolution order."""

    def test_exact_canonical_key_returned_as_is(self):
        from strategy.driving_advisor import _resolve_field_key
        # camber_front is already a canonical key
        assert _resolve_field_key("camber_front", "") == "camber_front"

    def test_all_canonical_keys_resolve_as_is(self):
        from strategy.driving_advisor import _resolve_field_key, _CANONICAL_SETUP_PARAMS
        for key in _CANONICAL_SETUP_PARAMS:
            assert _resolve_field_key(key, "") == key, (
                f"Canonical key '{key}' should resolve to itself"
            )

    def test_alias_brake_bias_front_resolves_to_brake_bias(self):
        from strategy.driving_advisor import _resolve_field_key
        assert _resolve_field_key("brake_bias_front", "") == "brake_bias", (
            "Alias 'brake_bias_front' must resolve to 'brake_bias'"
        )

    def test_setting_label_camber_front_resolves_to_camber_front(self):
        """Human-readable setting label 'Camber Front' → 'camber_front' via slug match.

        Note: slug('Camber Front') = 'camberfront' which exactly matches the canonical
        slug for 'camber_front'. Word-order matters: 'Front Camber' → 'frontcamber' does
        NOT match 'camberfront' (no substring relation), so the production AI is instructed
        to emit canonical keys directly rather than rely on arbitrary label ordering.
        """
        from strategy.driving_advisor import _resolve_field_key
        result = _resolve_field_key("", "Camber Front")
        assert result == "camber_front", (
            f"Setting label 'Camber Front' must resolve to 'camber_front', got {result!r}"
        )

    def test_setting_label_arb_front_resolves_to_arb_front(self):
        """Human-readable label 'ARB Front' → 'arb_front' via slug match."""
        from strategy.driving_advisor import _resolve_field_key
        result = _resolve_field_key("", "ARB Front")
        assert result == "arb_front", (
            f"Setting label 'ARB Front' must resolve to 'arb_front', got {result!r}"
        )

    def test_unrecognisable_label_returns_none(self):
        from strategy.driving_advisor import _resolve_field_key
        result = _resolve_field_key("xyzzy_unknown_param_99", "Some Unrecognised Label XYZ")
        assert result is None, (
            f"Unrecognisable field/setting must return None, got {result!r}"
        )

    def test_empty_field_and_setting_returns_none(self):
        from strategy.driving_advisor import _resolve_field_key
        assert _resolve_field_key("", "") is None

    def test_slug_match_on_field_value(self):
        """Field string 'camberFront' (camelCase) slug-matches 'camber_front'."""
        from strategy.driving_advisor import _resolve_field_key
        result = _resolve_field_key("camberFront", "")
        assert result == "camber_front", (
            f"Slug 'camberfront' should match 'camber_front', got {result!r}"
        )


class TestFixA_NormaliseChanges:
    """FIX A AC2 — _normalise_changes enriches each change with field + to_clamped."""

    def test_out_of_range_to_is_clamped_via_ranges(self):
        """Change with arb_front='15' but range (1,7) → to_clamped=7, to='15' preserved."""
        from strategy.driving_advisor import _normalise_changes
        from strategy.setup_ranges import GENERIC_DEFAULTS

        changes = [{"setting": "Front ARB", "field": "arb_front", "from": "4", "to": 15, "why": "test"}]
        # arb_front generic range is (1, 7)
        result = _normalise_changes(changes, setup_fields={}, car_name="")

        assert len(result) == 1
        ch = result[0]
        assert ch["field"] == "arb_front", f"field must be 'arb_front', got {ch['field']!r}"
        assert ch["to"] == 15, f"raw 'to' must be preserved as 15, got {ch['to']!r}"
        assert ch["to_clamped"] == 7, (
            f"to_clamped must be clamped to range max 7, got {ch['to_clamped']!r}"
        )

    def test_to_clamped_matches_setup_fields_when_present(self):
        """If setup_fields already carries the resolved param, to_clamped == setup_fields value."""
        from strategy.driving_advisor import _normalise_changes

        setup_fields = {"arb_front": 5}
        changes = [{"setting": "Front ARB", "field": "arb_front", "from": "4", "to": 99, "why": "test"}]
        result = _normalise_changes(changes, setup_fields=setup_fields, car_name="")

        ch = result[0]
        assert ch["to_clamped"] == 5, (
            f"to_clamped must come from setup_fields (5), not clamped raw (7), got {ch['to_clamped']!r}"
        )
        assert ch["to"] == 99, "raw 'to' must be preserved unchanged"

    def test_unresolvable_label_gives_none_field_and_raw_to_clamped(self):
        """Change whose label can't be resolved → field None, to_clamped falls back to raw to."""
        from strategy.driving_advisor import _normalise_changes

        changes = [{"setting": "XYZ Unknown Param", "field": "", "from": "?", "to": "some_value", "why": "test"}]
        result = _normalise_changes(changes, setup_fields={}, car_name="")

        ch = result[0]
        assert ch["field"] is None, f"Unresolvable field must be None, got {ch['field']!r}"
        assert ch["to_clamped"] == "some_value", (
            f"Unresolvable field must use raw 'to' as fallback, got {ch['to_clamped']!r}"
        )

    def test_original_changes_list_not_mutated(self):
        """_normalise_changes must return a new list; the caller's dicts must be unchanged."""
        from strategy.driving_advisor import _normalise_changes

        original = [{"setting": "Front ARB", "field": "arb_front", "from": "4", "to": 15}]
        import copy
        before = copy.deepcopy(original)
        _normalise_changes(original, setup_fields={}, car_name="")
        assert original == before, "_normalise_changes must not mutate the caller's list"

    def test_camber_clamped_to_zero_when_negative_and_positive_range(self):
        """camber_front to=-3.0 with generic range (0.0,6.0) → to_clamped=0.0."""
        from strategy.driving_advisor import _normalise_changes

        changes = [{"setting": "Front Camber", "field": "camber_front", "from": "1.0", "to": -3.0}]
        result = _normalise_changes(changes, setup_fields={}, car_name="")

        ch = result[0]
        assert ch["field"] == "camber_front"
        assert ch["to_clamped"] == 0.0, (
            f"Negative camber_front must clamp to 0.0, got {ch['to_clamped']!r}"
        )


class TestFixA_BuildCombinedSetupResponseWiring:
    """FIX A AC3 — build_combined_setup_response calls _normalise_changes and prompt instructs canonical field."""

    def test_build_combined_setup_response_calls_normalise_changes_source(self):
        """Source-scan: build_combined_setup_response body calls _normalise_changes."""
        assert "_normalise_changes" in _DRIVING_ADVISOR_SRC, (
            "driving_advisor.py must contain a call to _normalise_changes"
        )

    def test_prompt_instructs_canonical_field_key_source(self):
        """Source-scan: the combined prompt instructs AI that 'field' MUST be a canonical key."""
        assert "MUST be" in _DRIVING_ADVISOR_SRC and "canonical" in _DRIVING_ADVISOR_SRC, (
            "driving_advisor.py prompt must instruct AI that 'field' MUST be the canonical key"
        )

    def test_build_combined_response_normalises_out_of_range_to_clamped(self):
        """Group 42 REWRITE: call_api is now used for AI AUDIT only — not to generate changes.
        Changes come from the deterministic rule engine (plan_to_raw_data).
        The AI response JSON (with arb_front=15) is advisory metadata only and must NOT
        appear in the final changes list.

        This test verifies the Group 42 contract:
        1. call_api response does not drive the final changes list
        2. Rule engine changes (if any) go through _normalise_changes with to_clamped applied
        3. Unit-level _normalise_changes clamping is already covered by TestFixA_NormaliseChanges
        """
        from strategy.driving_advisor import DrivingAdvisor

        # Minimal mock recorder with one recent lap (no bottoming/wheelspin → rule engine
        # proposes 0 changes for an empty setup_dict — this is the correct behaviour)
        mock_recorder = MagicMock()
        mock_tracker = MagicMock()

        lap = MagicMock()
        lap.lap_num = 1
        lap.lap_time_ms = 90000
        lap.lock_up_count = 0
        lap.wheelspin_count = 0
        lap.oversteer_count = 0
        lap.oversteer_throttle_on_count = 0
        lap.kerb_count = 0
        lap.bottoming_count = 0
        lap.snap_throttle_count = 0
        lap.brake_consistency_m = 5.0
        lap.max_speed_kmh = 200.0
        lap.max_lat_g = 1.5
        lap.avg_throttle_pct = 60.0
        lap.avg_brake_pct = 20.0
        lap.rev_limiter_count = 0
        lap.lock_up_positions = []
        lap.wheelspin_positions = []
        lap.oversteer_positions = []
        lap.snap_throttle_positions = []
        lap.over_braking_positions = []
        lap.rev_limiter_by_gear = {}
        lap.over_braking_count = 0
        lap.abrupt_release_count = 0
        lap.car_max_speed_theoretical_kmh = 0.0
        lap.avg_tyre_radius = {}
        lap.off_track_count = 0
        mock_recorder.recent_laps.return_value = [lap]
        mock_recorder.best_lap.return_value = None

        config = {
            "anthropic": {"api_key": "fake-key", "model": None},
            "strategy": {"track": "Suzuka", "track_location_id": "", "layout_id": ""},
        }
        advisor = DrivingAdvisor(mock_recorder, mock_tracker, config)

        # Group 42: call_api is used for AI AUDIT only.
        # The AI response below contains arb_front=15 (out-of-range) but in Group 42
        # this is an audit response, not a changes-generating response.
        # The rule engine (not AI) decides what changes to propose.
        fake_audit_response = json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "Rule engine plan looks sound.",
        })

        with patch("strategy.driving_advisor.call_api", return_value=fake_audit_response):
            result_text = advisor.build_combined_setup_response({}, car_name="")

        result_data = json.loads(result_text)
        changes = result_data.get("changes", [])

        # Group 42 contract: changes come from the rule engine, not the AI response.
        # With an empty setup_dict and clean lap, the rule engine proposes no changes.
        # The AI audit response (arb_front=15) must NOT appear in changes.
        arb_changes = [ch for ch in changes if ch.get("field") == "arb_front"]
        assert arb_changes == [], (
            f"Group 42 contract: AI audit response must not inject arb_front changes. "
            f"Got arb_front changes: {arb_changes}"
        )

        # All changes that ARE present must come from the rule engine (have rule_id key)
        for ch in changes:
            assert "rule_id" in ch, (
                f"Group 42: all changes must come from rule engine (have 'rule_id'); "
                f"got: {ch}"
            )

        # The unit-level clamping contract (_normalise_changes) is covered in
        # TestFixA_NormaliseChanges — see test_out_of_range_to_is_clamped_via_ranges.


# ===========================================================================
# Fix B — Broadened parse exception in build_car_setup (strategy/ai_planner.py)
# ===========================================================================

class TestFixB_BroadenedParseException:
    """FIX B AC4 — structural errors (KeyError/ValueError) caught as cleanly as JSONDecodeError."""

    def test_both_calls_raise_key_error_produces_clean_runtime_error(self):
        """_parse_setup_recommendation raises KeyError on both calls → clean RuntimeError."""
        from strategy.ai_planner import build_car_setup

        # Provide valid JSON but missing ALL the required fields so _parse_setup_recommendation
        # will attempt to access a key that's absent — the clamp calls use .get() with defaults
        # so we need to force a KeyError by providing a range that's wrong type.
        # Simplest: return valid-looking JSON that causes a TypeError/ValueError during int() conversion.
        bad_json = json.dumps({
            "ride_height_front": "not_a_number_at_all_####",
            "dampers_front_comp": "also_bad",
        })

        def fake_call_api(prompt, **kwargs):
            return bad_json

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            with pytest.raises(RuntimeError) as exc_info:
                build_car_setup(**_BUILD_KWARGS)

        msg = str(exc_info.value)
        assert "Setup could not be generated" in msg, (
            f"RuntimeError must say 'Setup could not be generated', got: {msg!r}"
        )

    def test_first_call_structural_error_second_succeeds_returns_result(self):
        """If first call raises structural error, second succeeds → CarSetupRecommendation returned."""
        from strategy.ai_planner import build_car_setup, CarSetupRecommendation

        call_count = {"n": 0}

        def fake_call_api(prompt, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Valid JSON but causes ValueError during float() conversion in _parse_setup_recommendation
                return json.dumps({"ride_height_front": "INVALID_FLOAT", "reasoning": "ok"})
            # Second call returns fully valid JSON
            return _MINIMAL_SETUP_JSON

        with patch("strategy.ai_planner.call_api", side_effect=fake_call_api):
            result = build_car_setup(**_BUILD_KWARGS)

        assert isinstance(result, CarSetupRecommendation), (
            f"After structural error on first call and success on second, "
            f"must return CarSetupRecommendation, got {type(result)}"
        )
        assert call_count["n"] == 2

    def test_source_scan_broadened_except_clauses(self):
        """Source-scan: both except clauses in build_car_setup cover KeyError, ValueError, TypeError."""
        # Find the build_car_setup function body
        src = _AI_PLANNER_SRC
        func_start = src.find("def build_car_setup(")
        assert func_start != -1
        # Find the end of the function (next def at module level)
        func_end = src.find("\ndef ", func_start + 1)
        body = src[func_start:func_end] if func_end != -1 else src[func_start:]

        # Both except clauses should cover the broadened exception set
        assert "KeyError" in body, (
            "build_car_setup must catch KeyError (broadened exception)"
        )
        assert "ValueError" in body, (
            "build_car_setup must catch ValueError (broadened exception)"
        )
        assert "TypeError" in body, (
            "build_car_setup must catch TypeError (broadened exception)"
        )


# ===========================================================================
# Fix C — Camber clamp on range save (strategy/setup_ranges.py save_car_ranges)
# ===========================================================================

class TestFixC_SaveCarRangesCamberNormalisation:
    """FIX C AC5 — save_car_ranges normalises negative camber bounds before writing."""

    def _setup_tmp(self, monkeypatch, tmp_path):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()
        return tmp_file

    def test_negative_camber_front_saved_as_positive(self, monkeypatch, tmp_path):
        """min=-3.0, max=0.0 for camber_front → JSON written with min=0.0, max=3.0."""
        from strategy.setup_ranges import save_car_ranges
        tmp_file = self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("Legacy Car", {"camber_front": {"min": -3.0, "max": 0.0}})

        data = json.loads(tmp_file.read_text(encoding="utf-8"))
        saved = data["Legacy Car"]["camber_front"]
        assert saved["min"] >= 0 and saved["max"] >= 0, (
            f"Saved camber_front must have non-negative bounds, got {saved}"
        )
        assert saved["min"] == 0.0 and saved["max"] == 3.0, (
            f"Negative (-3.0, 0.0) must normalise to (0.0, 3.0), got {saved}"
        )

    def test_negative_camber_rear_both_negative_saved_as_positive(self, monkeypatch, tmp_path):
        """min=-4.0, max=-1.0 for camber_rear → JSON written with min=1.0, max=4.0."""
        from strategy.setup_ranges import save_car_ranges
        tmp_file = self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("Legacy Car", {"camber_rear": {"min": -4.0, "max": -1.0}})

        data = json.loads(tmp_file.read_text(encoding="utf-8"))
        saved = data["Legacy Car"]["camber_rear"]
        assert saved["min"] == 1.0 and saved["max"] == 4.0, (
            f"Negative (-4.0, -1.0) must normalise to (1.0, 4.0), got {saved}"
        )

    def test_non_camber_param_written_unchanged(self, monkeypatch, tmp_path):
        """Non-camber params must be written exactly as provided."""
        from strategy.setup_ranges import save_car_ranges
        tmp_file = self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("My Car", {"springs_front": {"min": 2.5, "max": 8.0}})

        data = json.loads(tmp_file.read_text(encoding="utf-8"))
        saved = data["My Car"]["springs_front"]
        assert saved["min"] == 2.5 and saved["max"] == 8.0, (
            f"springs_front must be written unchanged as (2.5, 8.0), got {saved}"
        )

    def test_resolve_ranges_after_save_returns_positive_camber(self, monkeypatch, tmp_path):
        """After saving negative camber bounds, resolve_ranges returns positive tuple."""
        from strategy.setup_ranges import save_car_ranges, resolve_ranges
        self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("Legacy Car", {"camber_front": {"min": -3.0, "max": 0.0}})

        result = resolve_ranges("Legacy Car")
        lo, hi = result["camber_front"]
        assert lo >= 0 and hi >= 0, (
            f"resolve_ranges after negative-camber save must return non-negative, got ({lo}, {hi})"
        )
        assert (lo, hi) == (0.0, 3.0), (
            f"resolve_ranges must return (0.0, 3.0) after saving (-3.0, 0.0), got ({lo}, {hi})"
        )

    def test_resolve_ranges_after_save_legacy_both_negative(self, monkeypatch, tmp_path):
        """After saving camber_rear (-4.0, -1.0), resolve_ranges returns (1.0, 4.0)."""
        from strategy.setup_ranges import save_car_ranges, resolve_ranges
        self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("Legacy Car", {"camber_rear": {"min": -4.0, "max": -1.0}})

        result = resolve_ranges("Legacy Car")
        lo, hi = result["camber_rear"]
        assert (lo, hi) == (1.0, 4.0), (
            f"resolve_ranges must return (1.0, 4.0) after saving (-4.0, -1.0), got ({lo}, {hi})"
        )


# ===========================================================================
# Fix 2 — Camber label (ui/setup_builder_ui.py)
# ===========================================================================

class TestFix2_CamberLabel:
    """FIX 2 AC6 — Camber label changed from 'Negative Camber Angle' to 'Camber Angle (°)'."""

    def test_negative_camber_angle_label_absent(self):
        assert "Negative Camber Angle" not in _SETUP_BUILDER_SRC, (
            "setup_builder_ui.py must not contain old label 'Negative Camber Angle'"
        )

    def test_camber_angle_label_present(self):
        assert "Camber Angle" in _SETUP_BUILDER_SRC, (
            "setup_builder_ui.py must contain the new label 'Camber Angle'"
        )


# ===========================================================================
# Fix 1 — Frontend uses to_clamped from backend (ui/setup_builder_ui.py)
# ===========================================================================

class TestFix1_FrontendUsesToClamped:
    """FIX 1 AC7 — _display_setup_result uses ch.get('to_clamped') and ch.get('field');
    old slug map (_ai_slug_map) is gone."""

    def test_display_uses_to_clamped(self):
        assert 'to_clamped' in _SETUP_BUILDER_SRC, (
            "_display_setup_result must reference 'to_clamped' from the change dict"
        )

    def test_display_uses_ch_get_to_clamped(self):
        """Verify the pattern ch.get('to_clamped'...) appears in the source."""
        assert 'ch.get("to_clamped"' in _SETUP_BUILDER_SRC or "ch.get('to_clamped'" in _SETUP_BUILDER_SRC, (
            "_display_setup_result must read to_clamped via ch.get()"
        )

    def test_display_uses_ch_get_field(self):
        """Verify ch.get('field') is used to identify resolved canonical param."""
        assert 'ch.get("field")' in _SETUP_BUILDER_SRC or "ch.get('field')" in _SETUP_BUILDER_SRC, (
            "_display_setup_result must read 'field' via ch.get() to identify resolved param"
        )

    def test_old_slug_map_absent(self):
        """The old _ai_slug_map slug-guessing approach must be removed."""
        assert "_ai_slug_map" not in _SETUP_BUILDER_SRC, (
            "Old '_ai_slug_map' slug map must be removed from setup_builder_ui.py "
            "(backend now resolves field via _normalise_changes)"
        )

    def test_no_inline_re_import_in_display_method(self):
        """The old 'import re as _re' inside _display_setup_result must be gone."""
        # Find just the _display_setup_result method body
        src = _SETUP_BUILDER_SRC
        method_start = src.find("def _display_setup_result(")
        assert method_start != -1, "def _display_setup_result not found"
        next_method = src.find("\n    def ", method_start + 1)
        body = src[method_start:next_method] if next_method != -1 else src[method_start:]
        assert "import re" not in body, (
            "Old 'import re' inside _display_setup_result must be removed "
            "(slug matching is now done server-side)"
        )


# ===========================================================================
# Fix D — feeling-fix path normalises changes (strategy/driving_advisor.py
#          build_driver_feeling_response)
# ===========================================================================

class TestFixD_FeelingResponseNormalisesChanges:
    """FIX D — build_driver_feeling_response calls _normalise_changes and
    the emitted JSON has `field` + `to_clamped` in each change item."""

    def test_source_scan_feeling_calls_normalise_changes(self):
        """Source-scan: build_driver_feeling_response calls _normalise_changes."""
        src = _DRIVING_ADVISOR_SRC
        # Find the method body
        start = src.find("def build_driver_feeling_response(")
        assert start != -1, "def build_driver_feeling_response not found"
        next_def = src.find("\n    def ", start + 1)
        body = src[start:next_def] if next_def != -1 else src[start:]
        assert "_normalise_changes" in body, (
            "build_driver_feeling_response must call _normalise_changes"
        )

    def _make_advisor(self):
        from strategy.driving_advisor import DrivingAdvisor
        from unittest.mock import MagicMock
        mock_recorder = MagicMock()
        # Return an empty list so the optional telemetry block in _build_feeling_prompt
        # is skipped (the `if recent:` guard short-circuits mean() calls on mock objects).
        mock_recorder.recent_laps.return_value = []
        mock_tracker = MagicMock()
        config = {
            "anthropic": {"api_key": "fake-key", "model": None},
            "strategy": {"track": "Suzuka"},
        }
        return DrivingAdvisor(mock_recorder, mock_tracker, config)

    def test_feeling_response_field_resolved_to_canonical_key(self):
        """Mock call_api returns JSON with camber_front change; field must be resolved."""
        import json as _json
        advisor = self._make_advisor()

        fake_response = _json.dumps({
            "analysis": "The car understeers.",
            "changes": [
                {
                    "setting": "Front Camber",
                    "field": "camber_front",
                    "from": "1.0",
                    "to": 9.0,
                    "why": "more grip",
                }
            ],
        })

        with patch("strategy.driving_advisor.call_api", return_value=fake_response):
            result_text = advisor.build_driver_feeling_response(
                "Car understeers in slow corners", {}, car_name=""
            )

        result_data = json.loads(result_text)
        changes = result_data.get("changes", [])
        assert len(changes) == 1
        ch = changes[0]
        assert ch.get("field") == "camber_front", (
            f"field must be canonical 'camber_front', got {ch.get('field')!r}"
        )

    def test_feeling_response_to_clamped_range_clamped(self):
        """camber_front to=9.0 with generic max 6.0 → to_clamped=6.0 via range-clamping.

        The feeling path passes empty setup_fields, so to_clamped comes from
        resolve_ranges, not from setup_fields.
        """
        import json as _json
        advisor = self._make_advisor()

        fake_response = _json.dumps({
            "analysis": "The car understeers.",
            "changes": [
                {
                    "setting": "Front Camber",
                    "field": "camber_front",
                    "from": "1.0",
                    "to": 9.0,
                    "why": "more grip",
                }
            ],
        })

        with patch("strategy.driving_advisor.call_api", return_value=fake_response):
            result_text = advisor.build_driver_feeling_response(
                "Car understeers in slow corners", {}, car_name=""
            )

        result_data = json.loads(result_text)
        ch = result_data["changes"][0]
        assert ch.get("to_clamped") == 6.0, (
            f"camber_front to=9.0 must clamp to generic max 6.0, got {ch.get('to_clamped')!r}"
        )

    def test_feeling_response_raw_to_preserved(self):
        """The raw `to` value must remain unchanged in the emitted JSON."""
        import json as _json
        advisor = self._make_advisor()

        fake_response = _json.dumps({
            "analysis": "Test.",
            "changes": [
                {"setting": "Front Camber", "field": "camber_front",
                 "from": "1.0", "to": 9.0, "why": "test"},
            ],
        })

        with patch("strategy.driving_advisor.call_api", return_value=fake_response):
            result_text = advisor.build_driver_feeling_response(
                "Understeers", {}, car_name=""
            )

        ch = json.loads(result_text)["changes"][0]
        assert ch.get("to") == 9.0, (
            f"Raw 'to' must be preserved as 9.0, got {ch.get('to')!r}"
        )

    def test_feeling_response_unresolvable_field_none(self):
        """A change with an unrecognisable label → field None, to_clamped == raw to."""
        import json as _json
        advisor = self._make_advisor()

        fake_response = _json.dumps({
            "analysis": "Test.",
            "changes": [
                {"setting": "Some Unknown Param XYZ", "field": "",
                 "from": "?", "to": "special_value", "why": "test"},
            ],
        })

        with patch("strategy.driving_advisor.call_api", return_value=fake_response):
            result_text = advisor.build_driver_feeling_response(
                "Car handles oddly", {}, car_name=""
            )

        ch = json.loads(result_text)["changes"][0]
        assert ch.get("field") is None, (
            f"Unresolvable field must be None, got {ch.get('field')!r}"
        )
        assert ch.get("to_clamped") == "special_value", (
            f"Unresolvable field must fall back to raw 'to', got {ch.get('to_clamped')!r}"
        )


# ===========================================================================
# Fix E — degenerate symmetric camber guard (strategy/setup_ranges.py
#          _normalise_camber_bounds)
# ===========================================================================

class TestFixE_NormaliseCamberBounds:
    """FIX E AC2 — unit-test _normalise_camber_bounds across all cases."""

    def test_negative_min_zero_max(self):
        """(-3.0, 0.0) → (0.0, 3.0)."""
        from strategy.setup_ranges import _normalise_camber_bounds
        assert _normalise_camber_bounds(-3.0, 0.0) == (0.0, 3.0), (
            "_normalise_camber_bounds(-3.0, 0.0) must return (0.0, 3.0)"
        )

    def test_both_negative(self):
        """(-4.0, -1.0) → (1.0, 4.0)."""
        from strategy.setup_ranges import _normalise_camber_bounds
        assert _normalise_camber_bounds(-4.0, -1.0) == (1.0, 4.0), (
            "_normalise_camber_bounds(-4.0, -1.0) must return (1.0, 4.0)"
        )

    def test_symmetric_degenerate(self):
        """(-6.0, 6.0) → (0.0, 6.0): abs gives (6.0, 6.0), degenerate guard sets lo=0."""
        from strategy.setup_ranges import _normalise_camber_bounds
        result = _normalise_camber_bounds(-6.0, 6.0)
        assert result == (0.0, 6.0), (
            f"_normalise_camber_bounds(-6.0, 6.0) must return (0.0, 6.0), got {result}"
        )

    def test_already_positive_unchanged(self):
        """(0.0, 6.0) → unchanged."""
        from strategy.setup_ranges import _normalise_camber_bounds
        assert _normalise_camber_bounds(0.0, 6.0) == (0.0, 6.0)

    def test_partial_positive_unchanged(self):
        """(0.5, 4.5) → unchanged."""
        from strategy.setup_ranges import _normalise_camber_bounds
        assert _normalise_camber_bounds(0.5, 4.5) == (0.5, 4.5)

    def test_zero_zero_degenerate_guard_not_triggered(self):
        """(0.0, 0.0) — lo==hi but lo==0 so degenerate guard does NOT fire."""
        from strategy.setup_ranges import _normalise_camber_bounds
        # Guard condition: lo == hi AND lo > 0 — with (0.0, 0.0) lo is not > 0
        assert _normalise_camber_bounds(0.0, 0.0) == (0.0, 0.0)

    def test_positive_degenerate_guard_fires(self):
        """(3.0, 3.0) — degenerate positive range → (0.0, 3.0)."""
        from strategy.setup_ranges import _normalise_camber_bounds
        # This can arise from (-3.0, 3.0) → abs → (3.0, 3.0) → guard → (0.0, 3.0)
        result = _normalise_camber_bounds(3.0, 3.0)
        assert result == (0.0, 3.0), (
            f"_normalise_camber_bounds(3.0, 3.0) must return (0.0, 3.0), got {result}"
        )


class TestFixE_SymmetricCamberEndToEnd:
    """FIX E AC3 — symmetric (-6.0, 6.0) camber entry yields (0.0, 6.0) end-to-end."""

    def _setup_tmp(self, monkeypatch, tmp_path):
        import strategy.setup_ranges as sr
        tmp_file = tmp_path / "car_setup_ranges.json"
        tmp_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(sr, "_JSON_PATH", tmp_file)
        sr._invalidate_cache()
        return tmp_file

    def test_resolve_ranges_symmetric_camber_gives_zero_to_max(self, monkeypatch, tmp_path):
        """resolve_ranges with stored (-6.0, 6.0) camber_front → (0.0, 6.0), not (6.0, 6.0)."""
        import strategy.setup_ranges as sr
        tmp_file = self._setup_tmp(monkeypatch, tmp_path)
        # Write a pre-normalised symmetric entry as if it came from an old save
        tmp_file.write_text(
            json.dumps({"My Car": {"camber_front": {"min": -6.0, "max": 6.0}}}),
            encoding="utf-8",
        )
        sr._invalidate_cache()

        result = sr.resolve_ranges("My Car")
        lo, hi = result["camber_front"]
        assert (lo, hi) == (0.0, 6.0), (
            f"Symmetric (-6.0, 6.0) must resolve to (0.0, 6.0), not ({lo}, {hi})"
        )

    def test_save_car_ranges_symmetric_camber_writes_zero_to_max(self, monkeypatch, tmp_path):
        """save_car_ranges with (-6.0, 6.0) camber_rear → JSON has min=0.0, max=6.0."""
        from strategy.setup_ranges import save_car_ranges
        tmp_file = self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("My Car", {"camber_rear": {"min": -6.0, "max": 6.0}})

        data = json.loads(tmp_file.read_text(encoding="utf-8"))
        saved = data["My Car"]["camber_rear"]
        assert saved["min"] == 0.0 and saved["max"] == 6.0, (
            f"Symmetric (-6.0, 6.0) must be saved as (0.0, 6.0), got {saved}"
        )

    def test_resolve_ranges_after_save_symmetric_camber(self, monkeypatch, tmp_path):
        """After saving (-6.0, 6.0), resolve_ranges returns (0.0, 6.0)."""
        from strategy.setup_ranges import save_car_ranges, resolve_ranges
        self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("My Car", {"camber_front": {"min": -6.0, "max": 6.0}})

        result = resolve_ranges("My Car")
        lo, hi = result["camber_front"]
        assert (lo, hi) == (0.0, 6.0), (
            f"resolve_ranges after symmetric save must return (0.0, 6.0), got ({lo}, {hi})"
        )

    def test_symmetric_not_locked_to_single_value(self, monkeypatch, tmp_path):
        """Confirm the old buggy result (6.0, 6.0) — which would make the range read-only —
        does NOT occur."""
        from strategy.setup_ranges import save_car_ranges, resolve_ranges
        self._setup_tmp(monkeypatch, tmp_path)

        save_car_ranges("My Car", {"camber_front": {"min": -6.0, "max": 6.0}})

        lo, hi = resolve_ranges("My Car")["camber_front"]
        assert not (lo == 6.0 and hi == 6.0), (
            "Symmetric camber must NOT produce the locked (6.0, 6.0) range"
        )
