"""`write_strategy` is a validated door, and a plan without a playbook is refused.

Until 7 Sep 2026 the MCP door stored whatever it was handed - no
`Handover.validate()` - so strategy 27 (Deep Forest) and 17 (Daytona) armed
George on his defaults, and a plan with a mistyped or forbidden action would
have armed too. The only two plans that ever carried a validated playbook came
through the CLI.
"""
from __future__ import annotations

import json

import pytest

from pitcrew.mcp import server
from pitcrew.store.db import Store

from .test_mcp_server import seeded  # noqa: F401 - the fixture


@pytest.fixture()
def door(seeded, monkeypatch):
    path, event_id = seeded
    monkeypatch.setattr(server, "_store", lambda: Store(path))
    return path, event_id


def _plan(**over):
    payload = {
        "author": "ludo",
        "stops": 1, "pit_laps": [10], "laps": 20,
        "stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0,
                    "start_lap": 1},
                   {"laps": 10, "compound": "RS", "fuel_l": 60.0,
                    "start_lap": 11, "tyres": False}],
        "binding_constraint": "fuel",
    }
    payload.update(over)
    return payload


def test_a_plan_with_no_playbook_is_refused_and_names_the_recipe(door):
    _path, event_id = door
    reply = json.loads(server.write_strategy(event_id, json.dumps(_plan())))
    assert reply["written"] is False
    assert "playbook" in reply["error"]
    assert "race-planner.md" in reply["error"]


def test_an_empty_playbook_is_accepted_as_no_adaptations(door):
    path, event_id = door
    reply = json.loads(server.write_strategy(
        event_id, json.dumps(_plan(playbook=[]))))
    assert reply["written"] is True
    store = Store(path)
    try:
        row = next(r for r in store.list_strategies(event_id)
                   if r["id"] == reply["strategyId"])
    finally:
        store.close()
    stored = row["plan"]
    assert stored["handover"]["playbook"] == []
    assert stored["handover"]["author"] == "ludo"
    assert "certificate" in stored["handover"]
    # The plan's own keys stay flat, where the coordinator reads them.
    assert stored["stints"][1]["tyres"] is False


def test_a_mistyped_action_is_refused_before_anything_is_stored(door):
    path, event_id = door
    before = len(Store(path).list_strategies(event_id))
    reply = json.loads(server.write_strategy(event_id, json.dumps(_plan(
        playbook=[{"trigger": "incident", "action": "recost_stints",
                   "when": "more than 8 s lost"}]))))
    assert reply["written"] is False
    assert reply["error"] == "playbook refused"
    assert any("recost_stints" in p for p in reply["problems"])
    assert len(Store(path).list_strategies(event_id)) == before


def test_a_forbidden_action_is_refused(door):
    _path, event_id = door
    reply = json.loads(server.write_strategy(event_id, json.dumps(_plan(
        playbook=[{"trigger": "fuel_short", "action": "fuel_map",
                   "when": "short"}]))))
    assert reply["written"] is False


def test_an_entry_without_when_is_refused(door):
    _path, event_id = door
    reply = json.loads(server.write_strategy(event_id, json.dumps(_plan(
        playbook=[{"trigger": "fuel_short", "action": "short_shift"}]))))
    assert reply["written"] is False
    assert any("no condition" in p for p in reply["problems"])


def test_the_reply_lists_the_unhandled_triggers(door):
    _path, event_id = door
    reply = json.loads(server.write_strategy(event_id, json.dumps(_plan(
        playbook=[{"trigger": "fuel_short", "action": "short_shift",
                   "when": "short by 0.5 lap"}]))))
    assert reply["written"] is True
    assert "stop_missed" in reply["unhandled"]
    assert "fuel_short" not in reply["unhandled"]


def test_the_race_screen_announces_itself_and_the_controller_listens():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    screen = (root / "ui" / "race_screen.py").read_text(encoding="utf-8")
    controller = (root / "controller.py").read_text(encoding="utf-8")
    assert "shown = pyqtSignal()" in screen
    assert "def showEvent" in screen
    assert "self.race_screen.shown.connect(self.refresh_plan)" in controller
    assert "def refresh_plan" in controller
    assert "def _poll_plan" in controller
