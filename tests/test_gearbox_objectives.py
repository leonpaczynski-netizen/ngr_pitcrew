"""Tests for strategy/gearbox_objectives + its display in the Garage (F2.6)."""

import pytest

from strategy.gearbox_objectives import gearbox_objectives, gearbox_headline


class TestGearboxObjectives:
    def test_qualifying_focuses_on_one_lap_pace(self):
        obj = " ".join(gearbox_objectives("qualifying")).lower()
        assert "one-lap" in obj and "top speed" in obj

    def test_race_focuses_on_consistency_and_fuel(self):
        obj = " ".join(gearbox_objectives("race")).lower()
        assert "consistent" in obj and "fuel" in obj and "wheelspin" in obj

    def test_qualifying_and_race_differ(self):
        # The whole point: not silently identical across disciplines.
        assert gearbox_objectives("qualifying") != gearbox_objectives("race")

    def test_base_is_baseline(self):
        assert any("baseline" in b.lower() for b in gearbox_objectives("base"))

    def test_headlines_are_discipline_specific(self):
        assert "one-lap" in gearbox_headline("qualifying").lower()
        assert "race pace" in gearbox_headline("race").lower()

    def test_never_raises(self):
        assert gearbox_objectives(None) == gearbox_objectives("")
        assert isinstance(gearbox_headline(None), str)


class TestGarageGearboxDisplay:
    def test_workspace_shows_discipline_specific_objectives(self):
        from PyQt6.QtWidgets import QApplication
        from ui.components.setup_workspace import SetupWorkspace
        from ui.setup_recommendation_vm import build_recommendation_vm
        _ = QApplication.instance() or QApplication([])
        w = SetupWorkspace()
        w.set_recommendation(build_recommendation_vm({}), discipline="qualifying")
        quali_text = w._gearbox.text().lower()
        w.set_recommendation(build_recommendation_vm({}), discipline="race")
        race_text = w._gearbox.text().lower()
        assert "one-lap" in quali_text
        assert "consistent" in race_text
        assert quali_text != race_text
