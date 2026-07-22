"""Tests for the Practice RunCard + VM (F3)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.run_card import RunCard, RunCardVM


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _plan():
    return {
        "objective": "Confirm the rear ARB change improves mid-corner rotation",
        "setup": "Quali v3",
        "changes": ["Rear ARB 5 -> 4", "Rear ride height 70 -> 74"],
        "expected_effect": "Less understeer through the Esses, no new instability on entry",
        "monitor": ["Turn 6 (Esses)", "Turn 10 entry"],
        "fuel": "12 L", "tyre": "Racing: Soft", "target_laps": "5",
        "push_level": "Qualifying push", "purpose": "diagnosis",
        "invalidation": ["A lock-up into Turn 1", "Off-track excursion"],
    }


class TestRunCardVM:
    def test_from_run_plan_maps_fields(self):
        vm = RunCardVM.from_run_plan(_plan())
        assert vm.objective.startswith("Confirm the rear ARB")
        assert vm.setup_label == "Quali v3"
        assert vm.changes == ("Rear ARB 5 -> 4", "Rear ride height 70 -> 74")
        assert vm.tyre == "Racing: Soft"
        assert vm.target_laps == "5"
        assert vm.purpose == "diagnosis"
        assert vm.invalidation[0] == "A lock-up into Turn 1"
        assert vm.has_plan is True

    def test_tolerant_key_naming(self):
        vm = RunCardVM.from_run_plan({"run_objective": "x", "changes_tested": ["a"],
                                      "fuel_load": "10 L", "run_type": "pace"})
        assert vm.objective == "x"
        assert vm.changes == ("a",)
        assert vm.fuel == "10 L"
        assert vm.purpose == "pace"

    def test_empty_and_garbage_safe(self):
        assert RunCardVM.from_run_plan(None).has_plan is False
        assert RunCardVM.from_run_plan("garbage").has_plan is False
        assert RunCardVM.from_run_plan({}).has_plan is False


class TestRunCard:
    def test_renders_plan_and_enables_start(self, qapp):
        c = RunCard()
        c.set_run(RunCardVM.from_run_plan(_plan()))
        assert "Esses" in c._objective.text() or "rotation" in c._objective.text()
        assert c._params["tyre"].text() == "Racing: Soft"
        assert c._params["purpose"].text() == "diagnosis"
        assert c._start.isEnabled() is True
        assert c._invalidation.isHidden() is False

    def test_start_emits(self, qapp):
        c = RunCard()
        c.set_run(RunCardVM.from_run_plan(_plan()))
        seen = []
        c.start_requested.connect(lambda: seen.append(True))
        c._start.click()
        assert seen == [True]

    def test_empty_plan_disables_start_and_shows_placeholder(self, qapp):
        c = RunCard()
        c.set_run(RunCardVM())
        assert c._start.isEnabled() is False
        assert c._empty.isHidden() is False

    def test_defensive_against_garbage(self, qapp):
        c = RunCard()
        c.set_run("not a vm")
        assert c._start.isEnabled() is False
