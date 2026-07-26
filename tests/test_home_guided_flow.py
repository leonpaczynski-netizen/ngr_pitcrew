"""Guided-flow (bouncing-ball) checks for the Home page: the DO-THIS-NEXT button is
never a dead end — with no active event it opens event management instead of sitting
disabled under a headline that tells the driver to act."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.home_page import HomePage
from ui.app_state import AppState


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestNoActiveEvent:
    def test_do_this_next_offers_to_create_or_activate(self, qapp):
        w = HomePage()
        w.render(AppState.empty(), None)
        assert w._next_is_manage is True
        assert w._btn_next.isEnabled() is True
        assert "activate" in w._btn_next.text().lower()

    def test_do_this_next_click_opens_event_management(self, qapp):
        w = HomePage()
        w.render(AppState.empty(), None)
        seen = []
        w.manage_events_requested.connect(lambda: seen.append(True))
        w._btn_next.click()
        assert seen == [True]

    def test_finish_button_hidden_without_an_active_event(self, qapp):
        w = HomePage()
        w.render(AppState.empty(), None)
        assert w._btn_finish.isHidden() is True
