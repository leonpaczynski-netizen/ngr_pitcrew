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


class _FakeDb:
    """Minimal stand-in for SessionDB recording what write_feedback was asked to store."""

    def __init__(self, sink):
        self._sink = sink

    def write_feedback(self, **kwargs):
        self._sink.append(kwargs)
        return len(self._sink)

    def get_dominant_setup_id(self, session_id):
        return 0

    def record_latest_lineage_outcome(self, *a, **kw):
        return None


def _revert_ok():
    from services.setup_service import SetupOutcome
    return SetupOutcome(ok=True, reason="Reverted to the previous values.")


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

    def test_strategy_approve_stays_on_strategy_until_start_race(self, wired):
        # Approving the plan is NOT starting the race — "Start Race" is the explicit next
        # step (fa7bafe). Approve must NOT jump to the Pit Wall (which stranded Start Race
        # a page away); it stays put and tells the driver to press Start Race.
        shell, win, _ = wired
        shell._navigate("strategy")
        shell.strategy_page.approve_requested.emit()
        assert shell.current_destination() != "live_pit_wall"

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
    def test_outcome_revert_goes_to_the_setup_engine(self, wired):
        """Revert is a sheet operation now, not a call into the classic form."""
        shell, _win, bridge = wired
        reverted = []
        bridge._setups.revert = lambda d="race": reverted.append(d) or _revert_ok()
        shell.practice_outcome.action_requested.emit("revert")
        assert reverted == ["race"]

    def test_feedback_persisted(self, wired):
        """UAT 2026-08-07 defect B1 — feedback must reach the session DB.

        This test used to assert against ``_Win.record_driver_feedback``, a method that
        exists ONLY on this stub: production code has no such method on any window, so
        the bridge's getattr probe always found nothing, the bare ``except: pass``
        swallowed it, and the test passed while every piece of new-shell feedback was
        discarded. It now asserts on the real collaborator — the session database.
        """
        shell, _win, bridge = wired
        written = []
        bridge._db = _FakeDb(written)
        shell.feedback_form._set_overall("worse")
        shell.feedback_form.submitted.emit({"overall": "worse", "traction": "Poor"})
        assert len(written) == 1
        assert written[0]["feedback"] == {"overall": "worse", "traction": "Poor"}

    def test_feedback_failure_is_reported_not_swallowed(self, wired):
        """A failed write must tell the driver, never look like a successful submit."""
        shell, _win, bridge = wired

        class _Boom:
            def write_feedback(self, **kw):
                raise RuntimeError("disk full")

        bridge._db = _Boom()
        shell.feedback_form.submitted.emit({"overall": "better"})
        assert "could not be saved" in shell.run_card._status.text().lower()

    def test_feedback_without_a_database_is_reported(self, wired):
        shell, _win, bridge = wired
        bridge._db = None
        shell.feedback_form.submitted.emit({"overall": "better"})
        assert "not saved" in shell.run_card._status.text().lower()

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
