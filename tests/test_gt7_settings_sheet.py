"""Tests for the GT7-style settings sheet (F2)."""

import pytest

from PyQt6.QtWidgets import QApplication

from PyQt6.QtWidgets import QLabel

from ui.components.gt7_settings_sheet import (
    GT7SettingsSheet, _LEFT_TITLES, _keys_for_label,
)
from ui import ngr_theme as _t


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

    def test_ballast_is_editable_and_emits_changes(self, qapp):
        s = GT7SettingsSheet()
        seen = []
        s.ballast_changed.connect(seen.append)
        # Load stored ballast (e.g. 109 kg to meet a minimum weight, biased rearward).
        s.set_ballast(ballast_kg=109, ballast_position=8)
        assert s._ballast_kg_spin.value() == 109
        assert s._ballast_pos_spin.value() == 8
        # Editing emits the change for the bridge to apply/persist.
        s._ballast_pos_spin.setValue(12)
        s._on_ballast_edited()
        assert seen and seen[-1] == {"ballast_kg": 109.0, "ballast_position": 12}

    def test_ballast_survives_a_setup_rerender(self, qapp):
        # The editable ballast section must persist across set_setup like the gearbox entry.
        s = GT7SettingsSheet()
        s.set_ballast(ballast_kg=90, ballast_position=-5)
        s.set_setup(_setup())
        assert s._ballast_kg_spin.value() == 90
        assert s._ballast_pos_spin.value() == -5

    def _green_values(self, sheet):
        """Text of every value box currently highlighted as changed (NGR_GREEN border)."""
        out = []
        for lbl in sheet.findChildren(QLabel):
            ss = lbl.styleSheet() or ""
            if _t.NGR_GREEN in ss and "border" in ss:
                out.append(lbl.text())
        return out

    def test_changed_field_in_every_section_highlights_not_just_suspension(self, qapp):
        # Regression: a recommendation changing an LSD (Differential & Brakes) value AND
        # an ARB (Suspension) value must highlight BOTH — previously only Tyres/Suspension
        # were in the section-key map, so the LSD change was never boxed.
        s = GT7SettingsSheet()
        setup = dict(_setup())
        setup["lsd_accel"] = 27
        s.set_setup(setup, changed_fields={"arb_front", "lsd_accel"})
        greens = self._green_values(s)
        assert "27" in greens, "LSD Accel (Differential) change must highlight"
        assert "5" in greens, "ARB front (Suspension) change must still highlight"

    def test_aero_and_transmission_changes_highlight(self, qapp):
        s = GT7SettingsSheet()
        s.set_setup(_setup(), changed_fields={"aero_rear", "final_drive"})
        greens = self._green_values(s)
        assert "590" in greens          # aero_rear from _setup()
        assert "3.900" in greens        # final_drive from _setup() (3-dp render)

    def test_keys_for_label_covers_all_sections(self, qapp):
        assert _keys_for_label("LSD Accel Sensitivity") == ("lsd_accel",)
        assert _keys_for_label("Anti-Roll Bar") == ("arb_front", "arb_rear")
        assert _keys_for_label("Downforce") == ("aero_front", "aero_rear")
        assert _keys_for_label("Ballast (kg)") == ("ballast_kg",)
        assert _keys_for_label("Gear 3") == ("gear_3", "gear_ratios")
        assert _keys_for_label("Unknown row") == ()

    def test_regulation_weight_and_power_are_editable_and_emit(self, qapp):
        s = GT7SettingsSheet()
        seen = []
        s.regulation_changed.connect(seen.append)
        s.set_regulation(weight_kg=1335, power_hp=606)      # Supercars BOP
        assert s._weight_spin.value() == 1335 and s._power_spin.value() == 606
        s._power_spin.setValue(600)
        s._on_regulation_edited()
        assert seen and seen[-1] == {"weight_kg": 1335.0, "power_hp": 600.0}
        # Survives a setup rerender.
        s.set_setup(_setup())
        assert s._weight_spin.value() == 1335
