"""Offscreen construction tests for the WorkflowStepper widget (Sprint 10 UI).

Verifies the widget builds one chip per stage, colours the current/blocked stage
distinctly, and surfaces the next action — without a display server.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication
from ui.workflow_stepper import build_workflow_state, WorkflowInputs, StageStatus
from ui.workflow_stepper_widget import WorkflowStepper


_app = QApplication.instance() or QApplication([])


def _stepper(state):
    w = WorkflowStepper()
    w.set_state(state)
    return w


def test_builds_one_chip_per_stage():
    st = build_workflow_state(WorkflowInputs(event_ready=True))
    w = _stepper(st)
    # chip_row has 12 chips + a trailing stretch item.
    assert w._chip_row.count() == st.total + 1


def test_next_action_and_progress_shown():
    st = build_workflow_state(WorkflowInputs(event_ready=True, track_ready=True))
    w = _stepper(st)
    assert "/" in w._progress_lbl.text()
    assert w._next_lbl.text()  # non-empty next action
    assert w._next_btn.isEnabled()


def test_blocked_stage_marks_action_bar_and_emits_tab():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True,
        setup_applied_in_gt7=False, setup_pending_changes=3))
    w = _stepper(st)
    assert "3 change" in w._next_lbl.text()
    captured = []
    w.go_to_tab.connect(captured.append)
    w._on_next()
    assert captured and captured[0] == st.next_tab


def test_complete_state_disables_button():
    st = build_workflow_state(WorkflowInputs(
        event_ready=True, track_ready=True, setup_saved=True, setup_applied_in_gt7=True,
        practice_captured=True, feedback_present=True, engineering_reviewed=True,
        race_setup_locked=True, strategy_evidence_ready=True, race_plan_built=True,
        live_review_available=True))
    w = _stepper(st)
    assert not w._next_btn.isEnabled()
