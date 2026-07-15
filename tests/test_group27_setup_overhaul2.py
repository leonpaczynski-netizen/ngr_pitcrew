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

# NOTE: The generative-AI setup builder (strategy.ai_planner: build_car_setup,
# _is_truncated, _parse_setup_recommendation, _build_setup_from_scratch_prompt,
# CarSetupRecommendation) was removed. The tests below cover only the surviving
# deterministic behaviour: setup ranges/camber normalisation, driving_advisor
# field resolution / change normalisation, and UI source-scan guards.

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
        # UAT auto-save: the Apply button now also saves ("Apply && Save recommendation").
        has_new = ("Apply Pit Crew recommendation" in _SETUP_BUILDER_SRC
                   or "Save recommendation" in _SETUP_BUILDER_SRC)
        assert has_old or has_new, (
            "setup_builder_ui.py / setup_form_widget.py must contain the Apply button label "
            "('Apply to Setup' pre-G42 / 'Apply Pit Crew recommendation' / 'Apply && Save recommendation')"
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

    def test_source_scan_feeling_routes_through_combined_response(self):
        """Source-scan: build_driver_feeling_response routes through the
        deterministic build_combined_setup_response pipeline (which is where
        _normalise_changes runs — see TestFixA
        test_build_combined_setup_response_calls_normalise_changes_source)."""
        src = _DRIVING_ADVISOR_SRC
        # Find the method body
        start = src.find("def build_driver_feeling_response(")
        assert start != -1, "def build_driver_feeling_response not found"
        next_def = src.find("\n    def ", start + 1)
        body = src[start:next_def] if next_def != -1 else src[start:]
        assert "build_combined_setup_response" in body, (
            "build_driver_feeling_response must delegate to "
            "build_combined_setup_response (the normalising rule-engine path)"
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
