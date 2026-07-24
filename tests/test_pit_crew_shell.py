"""Tests for the PitCrewShell (F1) — construction, navigation, state rendering."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.pit_crew_shell import PitCrewShell
from ui.pit_crew_controller import PitCrewController
from ui.app_state import build_app_state, NAV_DESTINATIONS
from ui import ngr_theme as theme
from data.event_context import build_event_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def shell(qapp):
    return PitCrewShell(PitCrewController())


class TestConstruction:
    def test_builds_all_pages_and_opens_on_home(self, shell):
        # Every nav destination has a page, plus the flows reached FROM a page rather
        # than from the rail (event setup is entered from Home, not navigated to).
        assert set(NAV_DESTINATIONS) <= set(shell._page_by_dest)
        assert set(shell._page_by_dest) - set(NAV_DESTINATIONS) == {"event_setup"}
        assert shell.current_destination() == "home"
        assert shell.nav._buttons["home"].isChecked() is True

    def test_has_persistent_chrome(self, shell):
        assert shell.header is not None
        assert shell.rail is not None
        assert shell.guidance is not None

    def test_every_page_scrolls_when_taller_than_the_viewport(self, shell):
        """UAT-7: "can't scroll on any page that has data below the visible window."
        Pages weren't wrapped, so the window opened taller than the screen and nothing
        scrolled. Every stack entry is now a vertical scroll area around the real page."""
        from PyQt6.QtWidgets import QScrollArea
        from PyQt6.QtCore import Qt
        for dest in NAV_DESTINATIONS:
            wrapper = shell._page_by_dest[dest]
            assert isinstance(wrapper, QScrollArea), dest
            assert wrapper.widgetResizable() is True
            assert (wrapper.verticalScrollBarPolicy()
                    == Qt.ScrollBarPolicy.ScrollBarAsNeeded), dest
            # The real page is reachable inside the wrapper (feeding still works).
            assert wrapper.widget() is not None

    def test_the_inner_page_is_still_reachable_for_feeding(self, shell):
        # The bridge feeds shell.garage_page etc.; wrapping must not hide them.
        assert shell._page_by_dest["garage"].widget() is shell.garage_page
        assert shell._page_by_dest["programme"].widget() is shell.programme_page


class TestNavigation:
    def test_nav_click_switches_page(self, shell):
        shell.nav._buttons["garage"].click()
        assert shell.current_destination() == "garage"
        assert shell.pages.currentWidget() is shell._page_by_dest["garage"]

    def test_progress_rail_stage_routes_to_nav(self, shell):
        shell._on_stage_selected("strategy")
        assert shell.current_destination() == "race_strategy"

    def test_guidance_primary_surface_navigates(self, shell):
        shell._on_guidance_surface("setup")   # setup -> garage
        assert shell.current_destination() == "garage"

    def test_unknown_surface_defaults_home(self, shell):
        shell._navigate("garage")
        shell._on_guidance_surface("nonsense")
        assert shell.current_destination() == "home"


class TestStateRendering:
    def test_controller_state_updates_chrome(self, shell):
        ev = build_event_context(
            event={"id": 5, "name": "Round 5"},
            strategy={"car": "GT-R", "track_location_id": "fuji"},
        )
        shell._controller.patch(event=ev, programme_stage="garage",
                                active_setup_label="Race v2", connected=True,
                                stage_states={"garage": theme.STAGE_CURRENT})
        assert "Round 5" in shell.header._event_line.text()
        assert "GT-R" in shell.header._ctx_line.text()
        assert shell.header._conn.tone == "success"
        # progress rail reflects the current stage
        assert "Current" in shell.rail._nodes["garage"].toolTip()

    def test_set_guidance_view_updates_card_and_home(self, shell):
        view = {
            "ok": True,
            "next_action": {"headline": "Bind the latest Practice session",
                            "detail": "A completed practice is unbound.",
                            "target_surface": "practice", "tone": "info"},
            "progress": {"practice_sessions": 2, "valid_laps": 18,
                         "setup_experiments": 1, "setup_confidence": "medium"},
            "attention": [],
            "quick_actions": [],
        }
        shell.set_guidance_view(view)
        assert shell.guidance._primary.text() == "Bind the latest Practice session"
        # Active Event was folded into Home — Home now carries the progress detail.
        assert "18 valid laps" in shell.home_page._evidence.text()

    def test_construct_with_default_controller(self, qapp):
        s = PitCrewShell()
        assert s.current_destination() == "home"
