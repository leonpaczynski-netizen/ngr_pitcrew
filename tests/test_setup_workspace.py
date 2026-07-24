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
        s.set_discipline("qualifying")
        assert s.current() == "qualifying"
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


class TestShiftRpmField:
    def test_setting_the_value_does_not_re_emit(self, qapp):
        w = SetupWorkspace()
        seen = []
        w.shift_rpm_changed.connect(seen.append)
        w.set_shift_rpm(7840, "note")
        assert w._shift_rpm.value() == 7840 and seen == []

    def test_a_periodic_feed_does_not_clobber_a_focused_edit(self, qapp):
        """UAT-7: "the rpm shift when I change it it changes straight back to default."
        The 750ms feed called set_shift_rpm mid-edit and reset the box the driver was
        typing in. While the field has focus its value is left alone."""
        w = SetupWorkspace()
        w.show()                                    # a shown widget can take focus
        w.set_shift_rpm(7840)
        w._shift_rpm.setFocus()
        if w._shift_rpm.hasFocus():                 # offscreen platforms may not focus
            w._shift_rpm.setValue(7000)             # the driver is mid-edit
            w.set_shift_rpm(7840, "feed note")      # a periodic feed lands
            assert w._shift_rpm.value() == 7000     # the edit is preserved
            assert w._shift_note.text() == "feed note"   # but the note still refreshes
        w.close()

    def test_an_edit_emits_the_new_value_once(self, qapp):
        w = SetupWorkspace()
        seen = []
        w.shift_rpm_changed.connect(seen.append)
        w.set_shift_rpm(7840)
        w._shift_rpm.setValue(7000)
        w._on_shift_rpm_edited()
        assert seen == [7000]
        w._on_shift_rpm_edited()                    # no change → no repeat emit
        assert seen == [7000]


class TestLockControl:
    """UAT-7: "how do I 'lock the base setup'?" The guidance CTA pointed at the Garage
    but there was nothing to click."""

    def test_hidden_until_the_setup_is_lockable(self, qapp):
        w = SetupWorkspace()
        w.set_lock_state(lockable=False, locked=False)
        assert w._lock_btn.isHidden() is True and w._pill_locked.isHidden() is True

    def test_lockable_shows_the_lock_button(self, qapp):
        w = SetupWorkspace()
        w.set_lock_state(lockable=True, locked=False, hint="converged")
        assert w._lock_btn.isHidden() is False
        assert w._lock_btn.text() == "Lock this setup"

    def test_locking_emits_the_current_discipline(self, qapp):
        w = SetupWorkspace()
        seen = []
        w.lock_requested.connect(lambda d, lk: seen.append((d, lk)))
        w._selector.set_discipline("qualifying")
        w.set_lock_state(lockable=True, locked=False)
        w._lock_btn.click()
        assert seen == [("qualifying", True)]

    def test_a_locked_setup_shows_the_pill_and_offers_reopen(self, qapp):
        w = SetupWorkspace()
        seen = []
        w.lock_requested.connect(lambda d, lk: seen.append((d, lk)))
        w.set_lock_state(lockable=True, locked=True)
        assert w._pill_locked.isHidden() is False
        assert w._lock_btn.text() == "Reopen setup"
        w._lock_btn.click()
        assert seen == [("race", False)]            # reopen, not re-lock

    def test_it_can_target_a_discipline_other_than_the_selected_tab(self, qapp):
        """UAT-8: "Lock the base setup" was stuck — base has no tab, so locking the
        selected tab never satisfied it. The button targets the nominated discipline."""
        w = SetupWorkspace()
        seen = []
        w.lock_requested.connect(lambda d, lk: seen.append((d, lk)))
        w._selector.set_discipline("race")           # on the Race tab
        w.set_lock_state(lockable=True, locked=False,
                         discipline="base", lock_label="Lock the base setup")
        assert w._lock_btn.text() == "Lock the base setup"
        w._lock_btn.click()
        assert seen == [("base", True)]              # locks base, not race
