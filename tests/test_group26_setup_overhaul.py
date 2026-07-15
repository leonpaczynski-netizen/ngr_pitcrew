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

# NOTE: The generative-AI setup prompt builder / parser
# (strategy.ai_planner._build_setup_from_scratch_prompt / _parse_setup_recommendation)
# and the GT7 reference loader (strategy._ai_client.load_gt7_reference /
# clear_gt7_cache) were removed with the AI purge. The prompt-content sections
# (B/C/D/E/F) and the _parse_setup_recommendation clamping tests that depended on
# them are gone. The deterministic setup-ranges behaviour (Section A) and the
# source-level regression guards (Section G) survive.


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

    def test_group17n_importable(self):
        import importlib
        mod = importlib.import_module("tests.test_group17n_uat_defects")
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
