"""Tests for the GT7-style settings sheet (F2)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.gt7_settings_sheet import GT7SettingsSheet, _LEFT_TITLES


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _setup():
    return {
        "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard",
        "ride_height_front": 60, "ride_height_rear": 70,
        "arb_front": 5, "arb_rear": 5,
        "dampers_front_comp": 30, "dampers_rear_comp": 30,
        "dampers_front_ext": 40, "dampers_rear_ext": 40,
        "springs_front": 3.50, "springs_rear": 3.50,
        "camber_front": 3.0, "camber_rear": 3.0,
        "toe_front": 0.10, "toe_rear": 0.20,
        "aero_front": 430, "aero_rear": 590,
        "lsd_initial": 15, "lsd_accel": 40, "lsd_decel": 50,
        "torque_distribution_rear": 100, "brake_bias_front": 0,
        "final_drive": 3.90, "transmission_max_speed_kmh": 300,
        "ballast_kg": 0, "power_restrictor": 100,
        "ecu_ingame": "Fully Customisable", "ecu_ingame_output": 100,
    }


def _count(layout):
    return sum(1 for i in range(layout.count()) if layout.itemAt(i).widget() is not None)


class TestGT7SettingsSheet:
    def test_populates_two_columns(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup(_setup())
        assert _count(s._left) >= 2      # Tyres + Suspension (+ Differential)
        assert _count(s._right) >= 1     # Aerodynamics etc.
        assert s._empty.isHidden() is True

    def test_left_column_holds_expected_sections(self, qapp):
        # Left titles are exactly the GT7 left-hand groups.
        assert _LEFT_TITLES == ("Tyres", "Suspension", "Differential & Brakes")

    def test_empty_setup_shows_empty_state(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup(None)
        assert s._empty.isHidden() is False
        assert _count(s._left) == 0

    def test_changed_fields_do_not_crash_and_render(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup(_setup(), changed_fields={"arb_rear", "ride_height_rear"})
        assert s._empty.isHidden() is True   # rendered fine with highlights

    def test_rerender_clears_previous(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup(_setup())
        first_left = _count(s._left)
        s.set_setup(_setup())               # re-render must not accumulate
        assert _count(s._left) == first_left

    def test_defensive_against_garbage(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup("not a dict")            # must not raise
        assert s._empty.isHidden() is False
