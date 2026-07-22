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


class _Auth:
    class _Active:
        label = "Race v2"
        applied = True
    def active_setup(self):
        return self._Active()


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
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        b.refresh()
        st = ctrl.state()
        assert st.car == "GT-R"
        assert st.connected is True
        assert st.active_setup_label == "Race v2"
        # Garage GT7 sheet shows the real current setup (arb rear 4).
        assert shell.garage_page._sheet._empty.isHidden() is True

    def test_disconnected_state(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow(connected=False)
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        b.refresh()
        assert ctrl.state().connected is False

    def test_none_window_is_safe(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        b = LiveShellBridge(shell, ctrl, window=None, config={})
        b.refresh()   # must not raise
        assert ctrl.state().has_active_event is False


class TestBridgeWriteSide:
    def test_apply_routes_to_form_apply(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        b._on_apply({"arb_rear": 4, "brake_bias_front": 52})
        assert win._race_form.applied_with == {"arb_rear": 4, "brake_bias_front": 52}

    def test_apply_via_garage_signal(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        shell.garage_page.apply_requested.emit({"arb_rear": 3})
        assert win._race_form.applied_with == {"arb_rear": 3}

    def test_revert_routes_to_window(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        b._on_revert("n2")
        assert win.reverted is True

    def test_empty_apply_is_noop(self, qapp):
        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _FakeWindow()
        b = LiveShellBridge(shell, ctrl, window=win, config={})
        b._on_apply({})
        assert win._race_form.applied_with is None
