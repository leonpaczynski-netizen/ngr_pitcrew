"""Tests for the F2 SetupWorkspace + discipline selector."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.setup_workspace import SetupWorkspace, SetupDisciplineSelector
from ui.setup_recommendation_vm import build_recommendation_vm


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _rec():
    return build_recommendation_vm({
        "changes": [
            {"field": "arb_rear", "setting": "Rear ARB", "from": 5, "to": 3,
             "to_clamped": 4, "confidence_level": "high",
             "rationale": "reduce mid-corner understeer", "symptom": "understeer"},
            {"field": "brake_bias_front", "setting": "Brake bias", "from": 52.0,
             "to": 54.0, "confidence_level": "medium"},
        ],
        "diagnosis": {"primary_issue": "Mid-corner understeer"},
    })


class TestDisciplineSelector:
    def test_defaults_to_race(self, qapp):
        s = SetupDisciplineSelector()
        assert s.current() == "race"
        assert s._buttons["race"].isChecked() is True

    def test_click_emits_and_updates(self, qapp):
        s = SetupDisciplineSelector()
        seen = []
        s.discipline_changed.connect(lambda d: seen.append(d))
        s._buttons["qualifying"].click()
        assert seen == ["qualifying"]
        assert s.current() == "qualifying"

    def test_set_discipline_no_emit(self, qapp):
        s = SetupDisciplineSelector()
        seen = []
        s.discipline_changed.connect(lambda d: seen.append(d))
        s.set_discipline("base")
        assert s.current() == "base"
        assert seen == []


class TestSetupWorkspace:
    def test_populates_changed_fields(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation(_rec(), discipline="qualifying",
                             active_setup="Quali v3", saved=True, applied=False)
        assert w._table.rowCount() == 2
        assert w._table.item(0, 0).text() == "Rear ARB"
        assert w._table.item(0, 2).text() == "4"   # clamped recommended value
        assert w._selector.current() == "qualifying"
        assert "Quali v3" in w._active.text()
        assert w._pill_saved.tone == "success"
        assert w._pill_applied.tone == "neutral"

    def test_apply_emits_unified_field_values(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation(_rec())
        seen = []
        w.apply_requested.connect(lambda d: seen.append(d))
        w._apply.click()
        assert seen and seen[0] == {"arb_rear": 4, "brake_bias_front": 54}

    def test_empty_recommendation_disables_apply(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation(build_recommendation_vm({}))
        assert w._table.rowCount() == 0
        assert w._apply.isEnabled() is False
        assert w._empty.isHidden() is False

    def test_explain_toggle(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation(_rec())
        assert w._why.isHidden() is True
        w._explain.setChecked(True)
        assert w._why.isHidden() is False
        assert "understeer" in w._why.text()

    def test_primary_issue_shown(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation(_rec())
        assert "Mid-corner understeer" in w._primary_issue.text()

    def test_defensive_against_garbage(self, qapp):
        w = SetupWorkspace()
        w.set_recommendation("not a vm")   # must not raise
        assert w._table.rowCount() == 0
