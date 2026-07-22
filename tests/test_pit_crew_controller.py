"""Tests for ui/pit_crew_controller.py (F0.3).

Verifies the controller holds one AppState, emits state_changed only on real
change, and patch() merges overrides over the current state.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.pit_crew_controller import PitCrewController
from ui.app_state import AppState, build_app_state
from ui import ngr_theme as theme
from data.event_context import build_event_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _capture(controller):
    seen = []
    controller.state_changed.connect(lambda s: seen.append(s))
    return seen


class TestController:
    def test_starts_empty(self, qapp):
        c = PitCrewController()
        assert isinstance(c.state(), AppState)
        assert c.state().has_active_event is False

    def test_set_state_emits_once_on_change(self, qapp):
        c = PitCrewController()
        seen = _capture(c)
        new = build_app_state(programme_stage="garage")
        assert c.set_state(new) is True
        assert len(seen) == 1
        assert seen[0].programme_stage == "garage"

    def test_set_state_dedups_equal_state(self, qapp):
        c = PitCrewController()
        seen = _capture(c)
        s1 = build_app_state(programme_stage="garage", connected=True)
        s2 = build_app_state(programme_stage="garage", connected=True)
        assert c.set_state(s1) is True
        assert c.set_state(s2) is False          # equal by value -> no re-emit
        assert len(seen) == 1

    def test_set_state_rejects_non_appstate(self, qapp):
        c = PitCrewController()
        seen = _capture(c)
        assert c.set_state("not a state") is False
        assert seen == []

    def test_patch_merges_over_current(self, qapp):
        c = PitCrewController()
        ev = build_event_context(strategy={"car": "GT-R", "track_location_id": "fuji"})
        c.set_state(build_app_state(event=ev, programme_stage="garage"))
        seen = _capture(c)
        # Patch only the stage; the event/car must carry over.
        out = c.patch(programme_stage="practice")
        assert out.car == "GT-R"
        assert out.programme_stage == "practice"
        assert c.state().programme_stage == "practice"
        assert len(seen) == 1

    def test_patch_validates_stage_states(self, qapp):
        c = PitCrewController()
        out = c.patch(stage_states={"garage": "bogus"})
        assert out.stage_state("garage") == theme.STAGE_AVAILABLE

    def test_patch_equal_result_does_not_emit(self, qapp):
        c = PitCrewController()
        c.set_state(build_app_state(connected=True))
        seen = _capture(c)
        c.patch(connected=True)   # no effective change
        assert seen == []
