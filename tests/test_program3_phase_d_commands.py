"""Program 3 Phase D2 — typed shell command vocabulary + dispatch (§10).

The typed commands are the auditable surface; dispatch routes the cleanly-mapping
ones to the canonical handler and refuses the rest explicitly (never silent, never
forced onto a semantically-different handler).
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell
from ui import shell_commands as cmd


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _bridge():
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    return LiveShellBridge(shell, ctrl, window=None, config={"strategy": {}})


def test_command_vocabulary_constructs():
    assert cmd.SelectEvent(event_id="e", event_name="Fuji").event_name == "Fuji"
    assert cmd.CompleteSessionRun(session_run_id="r").status == "complete"
    assert cmd.RecordDriverFeedback(feedback={"a": 1}).feedback == {"a": 1}


def test_dispatch_routes_clean_commands(qapp):
    b = _bridge()
    calls = {}
    b._on_activate_event = lambda name: calls.__setitem__("activate", name)
    b._on_start_run = lambda: calls.__setitem__("start", True)
    b._on_record_run = lambda: calls.__setitem__("record", True)
    b._on_feedback = lambda fb: calls.__setitem__("feedback", fb)

    b.dispatch(cmd.SelectEvent(event_name="Round 4 Fuji"))
    b.dispatch(cmd.StartSessionRun(session_type="practice"))
    b.dispatch(cmd.CompleteSessionRun(session_run_id="run-1"))
    b.dispatch(cmd.RecordDriverFeedback(feedback={"entry": "understeer"}))

    assert calls["activate"] == "Round 4 Fuji"
    assert calls["start"] is True
    assert calls["record"] is True
    assert calls["feedback"] == {"entry": "understeer"}


def test_deferred_commands_raise_not_implemented(qapp):
    b = _bridge()
    for c in (cmd.ApplySetup(setup_snapshot_id="x"),
              cmd.SelectSession(session_plan_id="p"),
              cmd.ResumeSessionRun(session_run_id="r"),
              cmd.ReportRaceIncident(session_run_id="r", incident="rain"),
              cmd.AcceptLearningProposal(learning_proposal_id="l"),
              cmd.RejectLearningProposal(learning_proposal_id="l")):
        with pytest.raises(NotImplementedError):
            b.dispatch(c)


def test_unknown_command_raises_type_error(qapp):
    b = _bridge()
    with pytest.raises(TypeError):
        b.dispatch(object())
