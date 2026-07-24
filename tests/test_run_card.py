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


class TestRunCardShowsHowToDriveIt:
    """UAT-6: the card never said what made THIS run different from the last one."""

    def test_driving_instructions_and_payoff_are_rendered(self, qapp):
        from strategy.run_brief import brief_for_domain
        b = brief_for_domain("driver_coaching")
        c = RunCard()
        c.set_run(RunCardVM(objective=b.objective, how_to_drive=b.how_to_drive,
                            monitor=b.monitor, reports=b.reports))
        assert c._how.isHidden() is False and c._how_cap.isHidden() is False
        assert c._reports.isHidden() is False
        assert b.how_to_drive[0] in c._how.text()
        assert b.monitor[0] in c._monitor.text()
        assert b.reports[0] in c._reports.text()

    def test_a_plan_without_them_hides_the_blocks_rather_than_showing_empty_headings(self, qapp):
        c = RunCard()
        c.set_run(RunCardVM(objective="Just drive"))
        assert c._how.isHidden() is True and c._how_cap.isHidden() is True
        assert c._monitor.isHidden() is True
        assert c._reports.isHidden() is True

    def test_two_domains_render_different_cards(self, qapp):
        from strategy.run_brief import brief_for_domain
        texts = []
        for domain in ("driver_coaching", "tyre_model"):
            b = brief_for_domain(domain)
            c = RunCard()
            c.set_run(RunCardVM(objective=b.objective, how_to_drive=b.how_to_drive,
                                monitor=b.monitor, reports=b.reports,
                                fuel=b.fuel, tyre=b.tyre, target_laps=b.target_laps,
                                push_level=b.push_level, purpose=b.purpose))
            texts.append((c._objective.text(), c._how.text(), c._monitor.text(),
                          c._params["fuel"].text(), c._params["push_level"].text()))
        assert texts[0] != texts[1]
        assert all(a != b for a, b in zip(*texts))

    def test_the_old_placeholder_can_no_longer_appear(self, qapp):
        """The bug the driver actually saw: "Monitor: whatever the coaching run is
        meant to show"."""
        from strategy.run_brief import brief_for_domain
        for domain in ("driver_coaching", "tyre_model", "fuel_model", "working_window"):
            b = brief_for_domain(domain)
            c = RunCard()
            c.set_run(RunCardVM(objective=b.objective, monitor=b.monitor))
            assert "whatever" not in c._monitor.text().lower()
