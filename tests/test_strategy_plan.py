"""Tests for the race strategy plan view (F5), including a safety check."""

import inspect
import pytest

from PyQt6.QtWidgets import QApplication, QPushButton

from ui.components.strategy_plan import (
    StrategyPlanView, StrategyPlanVM, StrategyOption, StrategyInput,
)
import ui.components.strategy_plan as strat_mod


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _vm():
    return StrategyPlanVM(
        options=(
            StrategyOption("2-stop (Soft-Soft-Medium)", total_time="1:02:14.3",
                           expected_laps="34", stints=("12 Soft", "12 Soft", "10 Medium"),
                           tyre_sequence="S→S→M", fuel_target="Full each stint",
                           pit_windows="L12, L24", confidence="high",
                           summary="Fastest total time on measured deg.", recommended=True),
            StrategyOption("1-stop (Medium-Hard)", total_time="1:02:48.9",
                           expected_laps="34", confidence="medium"),
        ),
        risks=(("Tyre deg", "medium"), ("Traffic", "low")),
        inputs=(
            StrategyInput("Tyre deg", "0.06 s/lap", "measured"),
            StrategyInput("Pit loss", "22 s", "manual"),
            StrategyInput("Fuel burn", "assumed default", "assumed"),
            StrategyInput("Safety car", "unknown", "missing"),
        ),
        replan_triggers=("Deg exceeds 0.10 s/lap", "A safety car in the first 10 laps"),
    )


class TestStrategyPlanView:
    def test_renders_and_enables_approve(self, qapp):
        w = StrategyPlanView()
        w.set_plan(_vm())
        assert w._vm.has_plan is True
        assert w._approve.isEnabled() is True

    def test_approve_emits(self, qapp):
        w = StrategyPlanView()
        w.set_plan(_vm())
        seen = []
        w.approve_requested.connect(lambda: seen.append(True))
        w._approve.click()
        assert seen == [True]

    def test_empty_disables_approve(self, qapp):
        w = StrategyPlanView()
        w.set_plan(StrategyPlanVM())
        assert w._approve.isEnabled() is False
        assert w._empty.isHidden() is False

    def test_defensive(self, qapp):
        w = StrategyPlanView()
        w.set_plan("garbage")
        assert w._approve.isEnabled() is False


class TestStrategySafety:
    def test_no_setup_apply_control_on_strategy_surface(self, qapp):
        # SAFETY: the strategy surface must never expose a setup Apply control.
        w = StrategyPlanView()
        w.set_plan(_vm())
        for btn in w.findChildren(QPushButton):
            text = (btn.text() or "").lower()
            assert "apply" not in text, f"unexpected apply control: {btn.text()!r}"
        # And the only primary action is Approve Race Plan.
        assert w._approve.text() == "Approve Race Plan"

    def test_source_has_no_setup_apply_tokens(self):
        src = inspect.getsource(strat_mod).lower()
        assert "apply_field" not in src
        assert "applied_field_values" not in src
        assert "mark_applied" not in src
