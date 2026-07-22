"""Tests for ui/new_shell_launch.py (F1 integration, flag-gated)."""

import os
import pytest

from PyQt6.QtWidgets import QApplication

from ui.new_shell_launch import (
    should_use_new_shell, build_initial_app_state, fetch_guidance_view,
    launch_new_shell,
)
from ui.pit_crew_shell import PitCrewShell
from data.event_context import build_event_context
from data.session_context import build_session_context


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class _FakeWindow:
    def _build_event_context(self):
        return build_event_context(
            event={"id": 9, "name": "Round 9"},
            strategy={"car": "GT-R", "track_location_id": "fuji"},
        )
    def _build_session_context(self):
        return build_session_context(connected=True, packet_count=5)
    def _build_strategy_context(self):
        return None  # exercises the None-context fallback


class _FakeDB:
    def build_event_command_centre_view(self, selected_cycle_id="", **_):
        return {"ok": True,
                "next_action": {"headline": "Bind the latest Practice session",
                                "detail": "One completed practice is unbound.",
                                "target_surface": "practice", "tone": "info"},
                "progress": {"practice_sessions": 1, "valid_laps": 8,
                             "setup_confidence": "low"},
                "attention": [], "quick_actions": []}


class TestShouldUseNewShell:
    def test_new_shell_is_the_default(self, monkeypatch):
        # Cutover (F9): the new shell is the default surface.
        monkeypatch.delenv("NGR_CLASSIC_UI", raising=False)
        assert should_use_new_shell({}) is True
        assert should_use_new_shell(None) is True
        assert should_use_new_shell({"ui": {}}) is True

    def test_classic_env_escape(self, monkeypatch):
        for v in ("1", "true", "YES", "on"):
            monkeypatch.setenv("NGR_CLASSIC_UI", v)
            assert should_use_new_shell({}) is False
        monkeypatch.setenv("NGR_CLASSIC_UI", "0")
        assert should_use_new_shell({}) is True

    def test_classic_config_escape(self, monkeypatch):
        monkeypatch.delenv("NGR_CLASSIC_UI", raising=False)
        assert should_use_new_shell({"ui": {"classic_shell": True}}) is False
        assert should_use_new_shell({"ui": {"classic_shell": False}}) is True


class TestPopulate:
    def test_build_initial_app_state_from_window(self):
        s = build_initial_app_state(_FakeWindow(), {})
        assert s.car == "GT-R"
        assert s.has_active_event is True
        assert s.connected is True

    def test_build_initial_app_state_none_window_is_empty(self):
        s = build_initial_app_state(None, {})
        assert s.has_active_event is False

    def test_fetch_guidance_view(self):
        assert fetch_guidance_view(None, {}) is None
        view = fetch_guidance_view(_FakeDB(), {"active_cycle_id": "cycle-x"})
        assert view["ok"] is True


class TestLaunch:
    def test_launch_returns_populated_shell(self, qapp):
        shell = launch_new_shell(window=_FakeWindow(), config={}, db=_FakeDB())
        assert isinstance(shell, PitCrewShell)
        assert shell._controller.state().car == "GT-R"
        assert shell.guidance._primary.text() == "Bind the latest Practice session"

    def test_launch_defensive_with_no_inputs(self, qapp):
        shell = launch_new_shell()
        assert isinstance(shell, PitCrewShell)
