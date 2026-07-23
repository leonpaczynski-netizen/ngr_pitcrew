"""Tests that every new-shell surface action routes to real behaviour (live wiring)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _Announcer:
    def __init__(self):
        self.spoken = None
    def speak(self, text):
        self.spoken = text


class _Form:
    def apply_ai_fields(self, f):
        pass


class _Win:
    def __init__(self):
        self.reverted = False
        self.selected_tab = None
        self.feedback = None
        self._announcer = _Announcer()
        self._race_form = _Form()
    def _revert_last_change_for_form(self, form):
        self.reverted = True
    def select_tab(self, key):
        self.selected_tab = key
    def record_driver_feedback(self, fb):
        self.feedback = fb


@pytest.fixture
def wired(qapp):
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    win = _Win()
    bridge = LiveShellBridge(shell, ctrl, window=win, config={})
    return shell, win, bridge


class TestNavigationActions:
    def test_run_card_start_without_an_event_stays_put(self, wired):
        """Starting a run now OPENS a preparation activity first. With no active event
        there is nothing to record against, so it reports instead of navigating away
        into a run that could never be captured (UAT-2 V-5)."""
        shell, win, _ = wired
        shell.run_card.start_requested.emit()
        assert shell.current_destination() != "live_pit_wall"
        assert "activate" in shell.run_card._status.text().lower()

    def test_qualifying_begin_goes_live(self, wired):
        shell, win, _ = wired
        shell.qualifying_page.begin_requested.emit()
        assert shell.current_destination() == "live_pit_wall"

    def test_strategy_approve_goes_live(self, wired):
        shell, win, _ = wired
        shell.strategy_page.approve_requested.emit()
        assert shell.current_destination() == "live_pit_wall"

    def test_debrief_close_goes_home(self, wired):
        shell, win, _ = wired
        shell._navigate("debrief")
        shell.debrief_page.action_requested.emit("close")
        assert shell.current_destination() == "home"

    def test_outcome_to_qualifying(self, wired):
        shell, win, _ = wired
        shell.practice_outcome.action_requested.emit("to_qualifying")
        assert shell.current_destination() == "qualifying"


class TestRealBehaviourActions:
    def test_outcome_revert_calls_window(self, wired):
        shell, win, _ = wired
        shell.practice_outcome.action_requested.emit("revert")
        assert win.reverted is True

    def test_feedback_persisted(self, wired):
        shell, win, _ = wired
        shell.feedback_form._set_overall("worse")
        shell.feedback_form.submitted.emit({"overall": "worse"})
        assert win.feedback == {"overall": "worse"}

    def test_library_open_never_raises_the_classic_window(self, wired):
        """The Library hosts engineering panels natively now — opening an area must
        not throw the driver back into the old dashboard (UAT-2 V-10)."""
        shell, win, _ = wired
        classic = []
        shell.classic_ui_requested.connect(lambda: classic.append(True))
        shell.library_page._buttons["knowledge_graph"].click()
        assert classic == []
        assert shell.library_page.showing_detail() is True

    def test_read_aloud_uses_announcer(self, wired):
        shell, win, _ = wired
        shell.guidance.read_aloud_requested.emit("Box this lap")
        assert win._announcer.spoken == "Box this lap"
