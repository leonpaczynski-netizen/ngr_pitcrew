"""Car weight distribution resolver — data/car_weight_distribution.py.

Tests cover:
  - Known car entry → float in (0, 1)
  - Unknown car → None
  - Empty name → None
  - Missing file → None, no exception
  - Caching: two calls with the same name return identical results
  - Value outside (0, 1) in JSON → None (guard)

All tests are Qt-free, offline, and use monkeypatch to avoid reading/writing
the real data file (which ships as ``{}`` by design).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _reset_cache(monkeypatch, data: dict) -> None:
    """Point the module at a fake in-memory cache so the real file is not read."""
    import data.car_weight_distribution as mod
    monkeypatch.setattr(mod, "_CACHE", data)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

class TestLookup:
    def test_known_car_returns_float(self, monkeypatch):
        _reset_cache(monkeypatch, {"Porsche 911 RSR (991) '17": 0.38})
        from data.car_weight_distribution import resolve_front_weight_dist
        result = resolve_front_weight_dist("Porsche 911 RSR (991) '17")
        assert isinstance(result, float)

    def test_known_car_value_in_open_unit_interval(self, monkeypatch):
        _reset_cache(monkeypatch, {"Porsche 911 RSR (991) '17": 0.38})
        from data.car_weight_distribution import resolve_front_weight_dist
        result = resolve_front_weight_dist("Porsche 911 RSR (991) '17")
        assert 0.0 < result < 1.0

    def test_known_car_value_matches_entry(self, monkeypatch):
        _reset_cache(monkeypatch, {"Honda NSX '17": 0.42})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Honda NSX '17") == pytest.approx(0.42)

    def test_unknown_car_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Totally Made Up Car") is None

    def test_unknown_car_not_in_populated_cache_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Real Car": 0.50})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Different Car") is None


# ---------------------------------------------------------------------------
# Edge cases for car_name
# ---------------------------------------------------------------------------

class TestEmptyName:
    def test_empty_string_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"": 0.50})  # even if "" is in cache, guard fires first
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("") is None

    def test_none_car_name_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {})
        from data.car_weight_distribution import resolve_front_weight_dist
        # The public contract is car_name: str; passing None tests the early guard
        assert resolve_front_weight_dist(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Missing / corrupt file
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_missing_file_returns_none_no_exception(self, tmp_path, monkeypatch):
        import data.car_weight_distribution as mod
        monkeypatch.setattr(mod, "_CACHE", None)
        monkeypatch.setattr(mod, "_PATH", tmp_path / "does_not_exist.json")
        from data.car_weight_distribution import resolve_front_weight_dist
        # Should not raise; must return None for every car name
        assert resolve_front_weight_dist("Any Car") is None

    def test_corrupt_json_returns_none_no_exception(self, tmp_path, monkeypatch):
        import data.car_weight_distribution as mod
        bad = tmp_path / "bad.json"
        bad.write_text("NOT VALID JSON", encoding="utf-8")
        monkeypatch.setattr(mod, "_CACHE", None)
        monkeypatch.setattr(mod, "_PATH", bad)
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Any Car") is None


# ---------------------------------------------------------------------------
# Value validation guard
# ---------------------------------------------------------------------------

class TestValueGuard:
    def test_value_gt_1_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Car A": 1.5})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Car A") is None

    def test_value_exactly_1_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Car B": 1.0})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Car B") is None

    def test_value_zero_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Car C": 0.0})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Car C") is None

    def test_negative_value_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Car D": -0.1})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Car D") is None

    def test_non_numeric_value_returns_none(self, monkeypatch):
        _reset_cache(monkeypatch, {"Car E": "unknown"})
        from data.car_weight_distribution import resolve_front_weight_dist
        assert resolve_front_weight_dist("Car E") is None


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching:
    def test_two_calls_same_name_return_identical_result(self, monkeypatch):
        _reset_cache(monkeypatch, {"Test Car": 0.45})
        from data.car_weight_distribution import resolve_front_weight_dist
        r1 = resolve_front_weight_dist("Test Car")
        r2 = resolve_front_weight_dist("Test Car")
        assert r1 == r2

    def test_cache_is_not_reset_between_calls(self, monkeypatch):
        import data.car_weight_distribution as mod
        # Set a known cache state
        monkeypatch.setattr(mod, "_CACHE", {"Cached Car": 0.48})
        from data.car_weight_distribution import resolve_front_weight_dist
        _ = resolve_front_weight_dist("Cached Car")
        # Cache should still be the same dict (not reloaded)
        assert mod._CACHE is not None
        assert "Cached Car" in mod._CACHE

    def test_real_json_file_is_readable_no_exception(self):
        """The real car_weight_distribution.json (ships as {}) must be parseable."""
        import data.car_weight_distribution as mod
        # Force a fresh load from disk by briefly nulling the cache
        import importlib
        importlib.reload(mod)
        # An empty file should still succeed: result is None for any car
        from data.car_weight_distribution import resolve_front_weight_dist
        result = resolve_front_weight_dist("Any Car Whatsoever")
        assert result is None   # {} → nothing to resolve
