"""Tests for the LiveShellBridge (read side + apply/revert routing).

Uses a duck-typed fake window/services so the bridge is exercised without a live
GT7 session. Confirms the shell's view-models are fed from the (fake) real services
and that Apply/Revert route back to the window's existing apply path.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.live_shell_bridge import LiveShellBridge
from ui.pit_crew_controller import PitCrewController
from ui.pit_crew_shell import PitCrewShell
from data.event_context import build_event_context
from data.session_context import build_session_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _config():
    """A realistic config. The setup engine resolves car/track from the DB + config —
    NOT from the window — so a setup is always scoped to a real car at a real track."""
    return {"strategy": {"car": "GT-R", "track": "Fuji Speedway"}}


class _Auth:
    """Mirrors the REAL ActiveSetupAuthority contract.

    The previous fake took no arguments and exposed ``label``/``applied`` attributes —
    none of which ``ActiveSetupAuthority``/``ActiveSetup`` actually have, so this test
    passed while the shipped shell could never read an active setup (UAT-2 V-9).
    """

    class _Active:
        def label(self):
            return "Race v2"

        @property
        def is_active_on_car(self):
            return True

    def active_setup(self, identity, purpose="Race"):
        return self._Active() if purpose == "Race" else None


class _Form:
    def __init__(self):
        self.applied_with = None
    def current_setup_dict(self):
        return {"ride_height_front": 60, "ride_height_rear": 74, "arb_front": 5,
                "arb_rear": 4, "aero_front": 430, "aero_rear": 590,
                "tyre_front": "Racing: Hard", "tyre_rear": "Racing: Hard"}
    def apply_ai_fields(self, fields):
        self.applied_with = dict(fields)


class _FakeWindow:
    def __init__(self, connected=True):
        self._connected = connected
        self._race_form = _Form()
        self._setup_authority = _Auth()
        self.reverted = False
    def _build_event_context(self):
        return build_event_context(event={"id": 3, "name": "Round 3"},
                                   strategy={"car": "GT-R", "track_location_id": "fuji"})
    def _build_session_context(self):
        return build_session_context(connected=self._connected, packet_count=9, laps_recorded=7)
    def _build_strategy_context(self):
        return None
    def _autosave_applied_setup(self, form):
        pass
    def _revert_last_change_for_form(self, form):
        self.reverted = True


class TestBridgeReadSide:
    def test_refresh_feeds_appstate_and_garage(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow(connected=True)
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        st = ctrl.state()
        assert st.car == "GT-R"
        assert st.connected is True
        assert st.active_setup_label == "Race v2"
        # The Garage sheet is fed from the STORE now. The classic form's in-progress
        # setup is SEEDED into it once, so nothing the driver had is lost on the switch.
        assert b._setups.sheet("race").get("arb_rear") == 4.0
        assert shell.garage_page._sheet._empty.isHidden() is True

    def test_disconnected_state(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow(connected=False)
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()
        assert ctrl.state().connected is False

    def test_none_window_is_safe(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        b = LiveShellBridge(shell, ctrl, window=None, config=_config())
        b.refresh()   # must not raise
        assert ctrl.state().has_active_event is False


class TestBridgeWriteSide:
    """Apply and revert go through the headless setup engine, not the classic form."""

    def _wired(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config=_config())
        b.refresh()          # seeds the store from the classic form
        return shell, win, b

    def test_apply_writes_the_sheet(self, qapp):
        _shell, _win, b = self._wired(qapp)
        b._on_apply({"arb_rear": 4, "brake_bias_front": 52})
        sheet = b._setups.sheet("race")
        assert sheet.get("arb_rear") == 4.0
        assert sheet.get("brake_bias_front") == 52.0

    def test_apply_via_garage_signal(self, qapp):
        shell, _win, b = self._wired(qapp)
        shell.garage_page.apply_requested.emit({"arb_rear": 3})
        assert b._setups.sheet("race").get("arb_rear") == 3.0

    def test_the_classic_form_is_kept_in_step_while_it_still_exists(self, qapp):
        """Transitional, removed in stage 6: the old window must never display numbers
        that disagree with the real sheet."""
        _shell, win, b = self._wired(qapp)
        b._on_apply({"arb_rear": 4})
        assert win._race_form.applied_with is not None
        assert win._race_form.applied_with["arb_rear"] == 4.0

    def test_revert_undoes_the_last_apply(self, qapp):
        _shell, _win, b = self._wired(qapp)
        before = b._setups.sheet("race").get("arb_rear")
        b._on_apply({"arb_rear": 4})
        b._on_revert("n2")
        assert b._setups.sheet("race").get("arb_rear") == before

    def test_revert_with_nothing_to_undo_is_safe(self, qapp):
        _shell, _win, b = self._wired(qapp)
        b._on_revert("n2")          # must not raise
        assert b._setups.sheet("race").get("arb_rear") == 4.0

    def test_empty_apply_changes_nothing(self, qapp):
        _shell, _win, b = self._wired(qapp)
        before = b._setups.sheet("race").as_dict()
        b._on_apply({})
        assert b._setups.sheet("race").as_dict() == before
