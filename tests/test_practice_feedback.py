"""Tests for the structured practice feedback form (F3.2)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.practice_feedback import StructuredFeedbackForm, FEEDBACK_FIELDS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestFeedbackForm:
    def test_empty_submit_is_empty_dict(self, qapp):
        f = StructuredFeedbackForm()
        seen = []
        f.submitted.connect(lambda d: seen.append(d))
        f._submit.click()
        assert seen == [{}]

    def test_overall_worse_captured(self, qapp):
        f = StructuredFeedbackForm()
        f._set_overall("worse")
        assert f.current_feedback()["overall"] == "worse"

    def test_structured_fields_captured(self, qapp):
        f = StructuredFeedbackForm()
        f._set_overall("better")
        f._combos["corner_entry"].setCurrentText("Understeer")
        f._combos["traction"].setCurrentText("Good")
        f._corners.setCurrentText("Turn 6 (Esses)")
        f._notes.setText("felt planted on exit")
        fb = f.current_feedback()
        assert fb["overall"] == "better"
        assert fb["corner_entry"] == "Understeer"
        assert fb["traction"] == "Good"
        assert fb["corners"] == "Turn 6 (Esses)"
        assert fb["notes"] == "felt planted on exit"

    def test_blank_fields_excluded(self, qapp):
        f = StructuredFeedbackForm()
        f._combos["rotation"].setCurrentText("OK")
        fb = f.current_feedback()
        assert fb == {"rotation": "OK"}   # only the set field, nothing blank

    def test_all_feedback_fields_present_as_combos(self, qapp):
        f = StructuredFeedbackForm()
        for key, _label, _opts in FEEDBACK_FIELDS:
            assert key in f._combos

    def test_submit_emits_current(self, qapp):
        f = StructuredFeedbackForm()
        f._set_overall("unchanged")
        seen = []
        f.submitted.connect(lambda d: seen.append(d))
        f._submit.click()
        assert seen and seen[0]["overall"] == "unchanged"

    def test_set_corner_options(self, qapp):
        f = StructuredFeedbackForm()
        f.set_corner_options(["Turn 1", "Turn 6 (Esses)", "Turn 10"])
        assert f._corners.count() == 3
