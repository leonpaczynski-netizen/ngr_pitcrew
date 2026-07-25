"""Adaptive Per-Gear Shift Strategy — store unit tests."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from services.shift_strategy_store import (
    ShiftStrategyStore,
    default_shift_strategy_path,
)
from services.setup_store import scope_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_path_str(tmp_path):
    return str(tmp_path / "shift_strategy.json")


def _sample_data(fingerprint: str = "abc123", med: dict = None) -> dict:
    return {
        "fingerprint": fingerprint,
        "computed_at": "2026-07-25T10:00:00Z",
        "manual_engine_data": med or {"peak_power_rpm": 7000, "peak_torque_rpm": 5500, "redline": 8000},
        "qualifying_profile_json": {"mode": "qualifying", "decisions": []},
        "race_profile_json": {"mode": "race", "decisions": []},
        "required_fuel_saving_pct": 5.0,
    }


# ---------------------------------------------------------------------------
# Save → reload round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_save_and_reload_preserves_all_fields(self, tmp_path_str):
        scope = scope_key("Porsche 963", "Spa", "Full Course")
        data = _sample_data("fp001")

        store = ShiftStrategyStore(path=tmp_path_str)
        ok = store.save(scope, data)
        assert ok is True

        store2 = ShiftStrategyStore(path=tmp_path_str)
        loaded = store2.get(scope)
        assert loaded is not None
        assert loaded["fingerprint"] == "fp001"
        assert loaded["computed_at"] == "2026-07-25T10:00:00Z"
        assert loaded["required_fuel_saving_pct"] == 5.0

    def test_manual_engine_data_preserved(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        med = {"peak_power_rpm": 6500, "peak_torque_rpm": 4000, "redline": 7500}
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope, _sample_data(med=med))

        loaded = ShiftStrategyStore(path=tmp_path_str).get(scope)
        assert loaded["manual_engine_data"] == med

    def test_fingerprint_preserved(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope, _sample_data("myfp123"))
        loaded = ShiftStrategyStore(path=tmp_path_str).get(scope)
        assert loaded["fingerprint"] == "myfp123"

    def test_qualifying_profile_json_preserved(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        qp = {"mode": "qualifying", "decisions": [{"from_gear": 1, "to_gear": 2, "valid": True}]}
        data = _sample_data()
        data["qualifying_profile_json"] = qp
        ShiftStrategyStore(path=tmp_path_str).save(scope, data)
        loaded = ShiftStrategyStore(path=tmp_path_str).get(scope)
        assert loaded["qualifying_profile_json"] == qp

    def test_multiple_scopes_independent(self, tmp_path_str):
        scope_a = scope_key("CarA", "TrackA", "")
        scope_b = scope_key("CarB", "TrackB", "")
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope_a, _sample_data("fpA"))
        store.save(scope_b, _sample_data("fpB"))

        store2 = ShiftStrategyStore(path=tmp_path_str)
        assert store2.get(scope_a)["fingerprint"] == "fpA"
        assert store2.get(scope_b)["fingerprint"] == "fpB"

    def test_overwrite_scope_replaces_data(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope, _sample_data("fp_old"))
        store.save(scope, _sample_data("fp_new"))
        loaded = ShiftStrategyStore(path=tmp_path_str).get(scope)
        assert loaded["fingerprint"] == "fp_new"


# ---------------------------------------------------------------------------
# Missing / absent scope
# ---------------------------------------------------------------------------

class TestMissingScope:
    def test_get_missing_scope_returns_none(self, tmp_path_str):
        store = ShiftStrategyStore(path=tmp_path_str)
        assert store.get(scope_key("Nobody", "Nowhere", "")) is None

    def test_get_from_empty_store_returns_none(self, tmp_path_str):
        store = ShiftStrategyStore(path=tmp_path_str)
        assert store.get("any_scope") is None

    def test_load_nonexistent_file_is_empty(self, tmp_path_str):
        assert not os.path.exists(tmp_path_str)
        store = ShiftStrategyStore(path=tmp_path_str)
        assert store.get("x") is None

    def test_load_corrupt_file_is_empty(self, tmp_path_str):
        with open(tmp_path_str, "w") as fh:
            fh.write("not json {{")
        store = ShiftStrategyStore(path=tmp_path_str)
        assert store.get("anything") is None


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestErrorPaths:
    def test_bad_path_returns_false_no_raise(self, tmp_path):
        # Use an existing regular FILE as the "directory" — writing inside
        # it must fail on every platform (a file cannot be a directory).
        existing_file = tmp_path / "i_am_a_file.json"
        existing_file.write_text("{}")
        bad_path = str(existing_file) + "/nested/shift_strategy.json"
        store = ShiftStrategyStore(path=bad_path)
        result = store.save("scope", _sample_data())
        assert result is False

    def test_no_path_save_returns_false(self):
        store = ShiftStrategyStore(path=None)
        assert store.save("scope", _sample_data()) is False

    def test_no_path_get_returns_none(self):
        store = ShiftStrategyStore(path=None)
        assert store.get("scope") is None

    def test_save_does_not_raise_on_unwritable_path(self, tmp_path):
        # Parent is an existing file — os.makedirs must raise, store catches it.
        existing_file = tmp_path / "blocker.json"
        existing_file.write_text("{}")
        bad_path = str(existing_file) + "/sub/file.json"
        store = ShiftStrategyStore(path=bad_path)
        try:
            result = store.save("scope", _sample_data())
            assert result is False
        except Exception as exc:
            pytest.fail(f"save() raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clear_removes_scope(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope, _sample_data())
        store.clear(scope)
        assert ShiftStrategyStore(path=tmp_path_str).get(scope) is None

    def test_clear_other_scope_untouched(self, tmp_path_str):
        scope_a = scope_key("A", "T", "")
        scope_b = scope_key("B", "T", "")
        store = ShiftStrategyStore(path=tmp_path_str)
        store.save(scope_a, _sample_data("fpA"))
        store.save(scope_b, _sample_data("fpB"))
        store.clear(scope_a)
        assert ShiftStrategyStore(path=tmp_path_str).get(scope_b)["fingerprint"] == "fpB"


# ---------------------------------------------------------------------------
# default_shift_strategy_path
# ---------------------------------------------------------------------------

class TestDefaultPath:
    def test_no_config_returns_empty(self):
        assert default_shift_strategy_path("") == ""
        assert default_shift_strategy_path(None) == ""

    def test_beside_config(self, tmp_path):
        config = str(tmp_path / "config.json")
        path = default_shift_strategy_path(config)
        assert path == str(tmp_path / "shift_strategy.json")

    def test_schema_in_saved_file(self, tmp_path_str):
        scope = scope_key("Car", "Track", "")
        ShiftStrategyStore(path=tmp_path_str).save(scope, _sample_data())
        with open(tmp_path_str) as fh:
            raw = json.load(fh)
        assert raw.get("schema") == "ngr.shift_strategy.v1"
