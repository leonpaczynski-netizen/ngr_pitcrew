"""Tests for the persistent shell chrome: ProgressRail, NavRail, EventHeaderBar (F1)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components import ProgressRail, NavRail, EventHeaderBar
from ui.app_state import build_app_state, AppState, PROGRAMME_STAGES, NAV_DESTINATIONS
from ui import ngr_theme as theme
from data.event_context import build_event_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestProgressRail:
    def test_has_all_eight_stages(self, qapp):
        rail = ProgressRail()
        assert set(rail._nodes.keys()) == set(PROGRAMME_STAGES)

    def test_blocked_stage_is_disabled_and_inert(self, qapp):
        rail = ProgressRail()
        rail.set_state(build_app_state(stage_states={
            "garage": theme.STAGE_COMPLETE,
            "qualifying": theme.STAGE_BLOCKED,
        }))
        assert rail._nodes["garage"].isEnabled() is True
        assert rail._nodes["qualifying"].isEnabled() is False
        # Clicking a blocked node emits nothing.
        seen = []
        rail.stage_selected.connect(lambda k: seen.append(k))
        rail._on_click("qualifying")
        assert seen == []
        rail._on_click("garage")
        assert seen == ["garage"]

    def test_state_word_in_tooltip_not_colour_only(self, qapp):
        rail = ProgressRail()
        rail.set_state(build_app_state(stage_states={"practice": theme.STAGE_CURRENT},
                                       programme_stage="practice"))
        assert "Current" in rail._nodes["practice"].toolTip()


class TestNavRail:
    def test_has_ten_destinations(self, qapp):
        nav = NavRail()
        assert set(nav._buttons.keys()) == set(NAV_DESTINATIONS)

    def test_click_emits_destination(self, qapp):
        nav = NavRail()
        seen = []
        nav.navigate.connect(lambda d: seen.append(d))
        nav._buttons["garage"].click()
        assert seen == ["garage"]

    def test_set_active_highlights_without_emitting(self, qapp):
        nav = NavRail()
        seen = []
        nav.navigate.connect(lambda d: seen.append(d))
        nav.set_active("debrief")
        assert nav._buttons["debrief"].isChecked() is True
        assert seen == []  # programmatic highlight must not emit navigate


class TestEventHeader:
    def test_binds_identity_and_connection(self, qapp):
        hdr = EventHeaderBar()
        ev = build_event_context(
            event={"id": 3, "name": "Round 3"},
            strategy={"car": "Porsche 911 RSR", "track_location_id": "watkins",
                      "layout_id": "long"},
        )
        hdr.bind(build_app_state(event=ev, active_setup_label="Quali v3",
                                 active_setup_applied=True, programme_stage="garage",
                                 connected=True))
        assert "Round 3" in hdr._event_line.text()
        assert "Porsche 911 RSR" in hdr._ctx_line.text()
        assert "Quali v3" in hdr._setup.text()
        assert "applied" in hdr._setup.text()
        assert hdr._conn.tone == "success"      # LIVE

    def test_empty_state_is_safe(self, qapp):
        hdr = EventHeaderBar()
        hdr.bind(AppState.empty())
        assert "No active event" in hdr._event_line.text()
        assert hdr._conn.tone == "neutral"      # NO SIGNAL

    def test_bind_defensive_against_garbage(self, qapp):
        hdr = EventHeaderBar()
        hdr.bind("not a state")   # must not raise
        assert hdr._event_line.text() != ""
