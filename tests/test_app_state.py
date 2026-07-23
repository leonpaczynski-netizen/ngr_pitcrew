"""Unit tests for ui/app_state.py — the canonical AppState spine (F0.3).

AppState must be Qt-free, immutable, never raise, aggregate the canonical
contexts without re-deriving them, and validate stage-state values against the
design-system tokens.
"""

import pytest

from ui.app_state import (
    AppState, build_app_state, PROGRAMME_STAGES, NAV_DESTINATIONS,
)
from ui import ngr_theme as theme
from data.event_context import build_event_context, EventContextSource
from data.session_context import build_session_context


class TestEmptyState:
    def test_empty_is_valid_and_has_no_active_event(self):
        s = AppState.empty()
        assert s.event.source == EventContextSource.EMPTY
        assert s.has_active_event is False
        assert s.car == s.event.car
        assert s.connected is False
        assert s.programme_stage == ""
        assert s.stage_states == ()

    def test_is_frozen(self):
        s = AppState.empty()
        with pytest.raises(Exception):
            s.connected = True  # frozen dataclass


class TestBuildAppState:
    def test_aggregates_passed_contexts_without_rederiving(self):
        ev = build_event_context(
            event={"id": 7, "name": "Round 3"},
            strategy={"car": "Porsche 911 RSR", "track_location_id": "watkins"},
        )
        se = build_session_context(connected=True, packet_count=10)
        s = build_app_state(
            event=ev, session=se,
            active_setup_label="Quali v3", active_setup_applied=True,
            programme_stage="garage", connected=True,
        )
        # Context objects are stored by identity — not copied/re-derived.
        assert s.event is ev
        assert s.session is se
        assert s.car == "Porsche 911 RSR"
        assert s.event_name == "Round 3"
        assert s.has_active_event is True
        assert s.active_setup_label == "Quali v3"
        assert s.active_setup_applied is True
        assert s.connected is True

    def test_missing_contexts_default_to_empty(self):
        s = build_app_state(programme_stage="briefing")
        assert s.event.source == EventContextSource.EMPTY
        assert s.programme_stage == "briefing"

    def test_never_raises_on_garbage(self):
        s = build_app_state(
            active_setup_label=None, active_setup_applied="yes",
            programme_stage=None, stage_states={"garage": "bogus-state"},
            connected="truthy",
        )
        assert s.active_setup_label == ""
        assert s.active_setup_applied is True
        assert s.programme_stage == ""
        assert s.connected is True


class TestStageStates:
    def test_unknown_state_falls_back_to_available(self):
        s = build_app_state(stage_states={"garage": "not-a-real-state"})
        assert s.stage_state("garage") == theme.STAGE_AVAILABLE

    def test_valid_states_are_preserved(self):
        s = build_app_state(stage_states={
            "briefing": theme.STAGE_COMPLETE,
            "garage": theme.STAGE_CURRENT,
            "qualifying": theme.STAGE_BLOCKED,
            "race": theme.STAGE_NOT_REQUIRED,
        })
        assert s.stage_state("briefing") == theme.STAGE_COMPLETE
        assert s.stage_state("garage") == theme.STAGE_CURRENT
        assert s.stage_state("unknown") == theme.STAGE_AVAILABLE  # default

    def test_can_navigate_blocks_blocked_and_not_required(self):
        s = build_app_state(stage_states={
            "garage": theme.STAGE_COMPLETE,
            "qualifying": theme.STAGE_BLOCKED,
            "race": theme.STAGE_NOT_REQUIRED,
        })
        assert s.can_navigate("garage") is True
        assert s.can_navigate("qualifying") is False
        assert s.can_navigate("race") is False
        assert s.can_navigate("practice") is True  # unknown -> available -> navigable

    def test_is_current_stage(self):
        s = build_app_state(programme_stage="practice")
        assert s.is_current_stage("practice") is True
        assert s.is_current_stage("garage") is False


class TestCanonicalConstants:
    def test_programme_stages_are_the_eight_rail_stages(self):
        assert PROGRAMME_STAGES == (
            "briefing", "garage", "practice", "review",
            "qualifying", "strategy", "race", "debrief",
        )

    def test_nav_covers_every_destination_and_leads_with_home(self):
        assert NAV_DESTINATIONS[0] == "home"
        for dest in ("engineering_library", "settings", "track_model"):
            assert dest in NAV_DESTINATIONS
        assert len(set(NAV_DESTINATIONS)) == len(NAV_DESTINATIONS)

    def test_every_destination_has_a_nav_label(self):
        """A destination with no label renders as a raw key in the rail."""
        from ui.components.nav_rail import NAV_LABELS
        assert set(NAV_DESTINATIONS) <= set(NAV_LABELS)


class TestQtFree:
    def test_module_imports_no_qt(self):
        # app_state must declare no Qt import at module scope. Assert on the source
        # rather than reloading the module — reloading would create a second
        # AppState class and break isinstance() for every later test in the suite.
        import inspect
        import ui.app_state as aps
        src = inspect.getsource(aps)
        assert "PyQt6" not in src and "QtWidgets" not in src
