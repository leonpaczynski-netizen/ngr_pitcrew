"""CarWeightDistStore — persisted user overlay for front weight-distribution.

Tests:
  - set → persist round-trip: write via one instance, read via a SECOND instance
    on the same tmp path (mirrors test_setup_history_store.py::TestPersistence)
  - missing file → empty overlay
  - corrupt file → empty, no raise
  - non-dict JSON → empty, no raise
  - file containing out-of-range values → valid ones kept, bad ones skipped
  - "" path → in-memory only, set returns True, nothing written
  - out-of-range frac (0, 1, -0.1, 1.5) → rejected, returns False, not stored
  - boundary values just inside open interval accepted
  - overlay() returns a COPY, not a reference to internal state
  - remove() deletes an existing entry and persists across reload
  - default_car_weight_dist_path ends with the expected filename
  - default_car_weight_dist_path("") == ""

All tests are Qt-free and offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from services.car_weight_dist_store import CarWeightDistStore, default_car_weight_dist_path


def _store(tmp_path, filename="car_weight_dist.user.json"):
    return CarWeightDistStore(str(tmp_path / filename))


# ---------------------------------------------------------------------------
# set → persist round-trip
# ---------------------------------------------------------------------------

class TestSetAndPersist:
    def test_set_returns_true_on_valid_fraction(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Porsche 911", 0.42) is True

    def test_round_trip_second_instance_reads_same_value(self, tmp_path):
        """Write via one store instance, read back via a SECOND — the restart case."""
        s1 = _store(tmp_path)
        s1.set("Porsche 911", 0.42)
        s2 = _store(tmp_path)
        assert s2.overlay().get("Porsche 911") == pytest.approx(0.42)

    def test_multiple_cars_all_persisted(self, tmp_path):
        s1 = _store(tmp_path)
        s1.set("Car A", 0.40)
        s1.set("Car B", 0.55)
        s2 = _store(tmp_path)
        ov = s2.overlay()
        assert ov["Car A"] == pytest.approx(0.40)
        assert ov["Car B"] == pytest.approx(0.55)

    def test_updating_a_car_overwrites_previous_value(self, tmp_path):
        s = _store(tmp_path)
        s.set("Car A", 0.40)
        s.set("Car A", 0.45)
        assert s.overlay()["Car A"] == pytest.approx(0.45)

    def test_updated_value_persists_across_reload(self, tmp_path):
        s1 = _store(tmp_path)
        s1.set("Car A", 0.40)
        s1.set("Car A", 0.45)
        s2 = _store(tmp_path)
        assert s2.overlay()["Car A"] == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Fraction validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_zero_is_rejected(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", 0.0) is False
        assert "Car" not in s.overlay()

    def test_one_is_rejected(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", 1.0) is False
        assert "Car" not in s.overlay()

    def test_negative_is_rejected(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", -0.1) is False
        assert "Car" not in s.overlay()

    def test_greater_than_one_is_rejected(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", 1.5) is False
        assert "Car" not in s.overlay()

    def test_rejected_value_not_stored(self, tmp_path):
        """Rejection must leave the overlay completely unchanged."""
        s = _store(tmp_path)
        s.set("Good Car", 0.42)
        s.set("Bad Car", 0.0)
        assert "Bad Car" not in s.overlay()
        assert "Good Car" in s.overlay()

    def test_boundary_just_above_zero_accepted(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", 0.001) is True

    def test_boundary_just_below_one_accepted(self, tmp_path):
        s = _store(tmp_path)
        assert s.set("Car", 0.999) is True


# ---------------------------------------------------------------------------
# Persistence / file handling
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_missing_file_is_empty_overlay(self, tmp_path):
        s = CarWeightDistStore(str(tmp_path / "nonexistent.json"))
        assert s.overlay() == {}

    def test_corrupt_file_degrades_to_empty_no_raise(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{ not json", encoding="utf-8")
        s = CarWeightDistStore(str(p))
        assert s.overlay() == {}

    def test_non_dict_json_degrades_to_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        s = CarWeightDistStore(str(p))
        assert s.overlay() == {}

    def test_file_with_out_of_range_values_skips_them(self, tmp_path):
        p = tmp_path / "overlay.json"
        p.write_text(
            '{"Car A": 0.42, "Car B": 1.5, "Car C": 0.0, "Car D": -0.1}',
            encoding="utf-8",
        )
        s = CarWeightDistStore(str(p))
        ov = s.overlay()
        assert ov.get("Car A") == pytest.approx(0.42)
        assert "Car B" not in ov
        assert "Car C" not in ov
        assert "Car D" not in ov

    def test_empty_path_set_returns_true(self):
        s = CarWeightDistStore("")
        assert s.set("Car", 0.42) is True

    def test_empty_path_value_accessible_in_memory(self):
        s = CarWeightDistStore("")
        s.set("Car", 0.42)
        assert s.overlay().get("Car") == pytest.approx(0.42)

    def test_overlay_returns_a_copy_not_a_reference(self, tmp_path):
        s = _store(tmp_path)
        s.set("Car", 0.42)
        ov = s.overlay()
        ov["mutated"] = 0.99
        assert "mutated" not in s.overlay()


# ---------------------------------------------------------------------------
# remove()
# ---------------------------------------------------------------------------

class TestRemove:
    def test_remove_existing_entry_returns_true(self, tmp_path):
        s = _store(tmp_path)
        s.set("Car", 0.42)
        assert s.remove("Car") is True

    def test_remove_existing_entry_absent_from_overlay(self, tmp_path):
        s = _store(tmp_path)
        s.set("Car", 0.42)
        s.remove("Car")
        assert "Car" not in s.overlay()

    def test_remove_nonexistent_returns_false(self, tmp_path):
        s = _store(tmp_path)
        assert s.remove("Nonexistent") is False

    def test_remove_persists_across_reload(self, tmp_path):
        s1 = _store(tmp_path)
        s1.set("Car", 0.42)
        s1.remove("Car")
        s2 = _store(tmp_path)
        assert "Car" not in s2.overlay()


# ---------------------------------------------------------------------------
# default_car_weight_dist_path
# ---------------------------------------------------------------------------

class TestDefaultPath:
    def test_ends_with_expected_filename(self):
        result = default_car_weight_dist_path("/x/y/config.json")
        assert result.endswith("car_weight_distribution.user.json")

    def test_empty_string_returns_empty_string(self):
        assert default_car_weight_dist_path("") == ""

    def test_whitespace_returns_empty_string(self):
        assert default_car_weight_dist_path("   ") == ""

    def test_sits_beside_the_config(self, tmp_path):
        cfg = str(tmp_path / "config.json")
        result = default_car_weight_dist_path(cfg)
        assert Path(result).parent == tmp_path
