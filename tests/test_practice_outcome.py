"""Tests for the practice outcome view (F3.4)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.practice_outcome import PracticeOutcome, PracticeOutcomeVM


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _improved():
    return PracticeOutcomeVM(
        verdict="improved", verdict_summary="The rear ARB change worked — rotation up, no new instability.",
        telemetry_findings=("Mid-corner min speed +1.8 km/h at Turn 6",),
        feedback_summary="Better than previous; less understeer mid-corner",
        agreements=("Both show improved mid-corner rotation",),
        contradictions=(),
        changed_vs_previous=("Rear ARB 5->4", "Rear ride height 70->74"),
        confidence="high",
        primary_action_label="Keep change & build next", primary_action_key="keep",
        secondary_action_label="Prepare qualifying", secondary_action_key="to_qualifying",
    )


def _worse():
    return PracticeOutcomeVM(
        verdict="worse", verdict_summary="Slower and less stable — revert.",
        contradictions=("Driver felt faster but telemetry is 0.3s slower",),
        confidence="medium",
        primary_action_label="Revert change", primary_action_key="revert",
    )


class TestPracticeOutcome:
    def test_improved_renders_and_primary_key(self, qapp):
        w = PracticeOutcome()
        w.set_outcome(_improved())
        assert w._verdict.tone == "success"
        assert w._confidence.level == "high"
        seen = []
        w.action_requested.connect(lambda k: seen.append(k))
        w._primary.click()
        assert seen == ["keep"]

    def test_worse_is_danger_tone_and_revert(self, qapp):
        w = PracticeOutcome()
        w.set_outcome(_worse())
        assert w._verdict.tone == "danger"      # worse is prominent
        seen = []
        w.action_requested.connect(lambda k: seen.append(k))
        w._primary.click()
        assert seen == ["revert"]
        assert w._contradictions.isHidden() is False

    def test_secondary_action(self, qapp):
        w = PracticeOutcome()
        w.set_outcome(_improved())
        seen = []
        w.action_requested.connect(lambda k: seen.append(k))
        w._secondary.click()
        assert seen == ["to_qualifying"]

    def test_empty_shows_placeholder(self, qapp):
        w = PracticeOutcome()
        w.set_outcome(PracticeOutcomeVM())
        assert w._empty.isHidden() is False
        assert w._primary.isEnabled() is False

    def test_defensive(self, qapp):
        w = PracticeOutcome()
        w.set_outcome("garbage")
        assert w._empty.isHidden() is False
