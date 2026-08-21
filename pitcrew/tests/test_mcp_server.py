"""The brain's seam into the app, driven over real stdio MCP.

Two things are being asserted and only one of them is about plumbing.

**The plumbing:** a client can connect, list the tools and get real rows back
out of the store.

**The discipline, which matters more:** *reads are open and writes only
propose.* `CLAUDE.md` §4.1 makes the driver's report primary evidence, and the
17 Aug audit priced what happens when the app is wrong about which sheet was in
the car - three sessions out of three, and a diagnosis that would have been
completely coherent about a car that was not on the circuit. A tool that could
write a sheet or arm a plan would be deciding something only he knows.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def call(tool: str, args: dict | None = None, *, db: str) -> dict | list:
    """Run one tool against a throwaway database, over a real stdio session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        import os

        env = dict(os.environ, PITCREW_DB=db, PYTHONPATH=str(REPO))
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "pitcrew.mcp.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                got = await session.call_tool(tool, args or {})
                return json.loads(got.content[0].text)

    return asyncio.run(run())


@pytest.fixture()
def seeded(tmp_path):
    """A database with one event, one sheet and one lap, on disk."""
    from pitcrew.setup.sheet import SetupSheet
    from pitcrew.store.db import Store
    from pitcrew.telemetry.session_state import Lap

    path = str(tmp_path / "pitcrew.db")
    store = Store(path)
    event_id = store.create_event(
        name="Monza", track="Autodromo Nazionale Monza", layout="Full",
        car_name="Porsche 911 RSR (991) '17", race_type="laps", race_laps=20,
        tyre_wear_mult="8x", fuel_mult="3x", game_version="1.71")
    store.save_setup_sheet(SetupSheet(
        car_name="Porsche 911 RSR (991) '17", sheet_name="Monza race",
        purpose="race", values={"rh_f": 60, "rh_r": 68},
        gears=[2.727, 1.925], shift_rpm={1: 7400.0}))
    session_id = store.start_session(event_id, "practice", game_version="1.71")
    store.add_lap(session_id, Lap(
        lap_num=1, lap_time_ms=110_000, best_lap_ms=110_000, delta_ms=0,
        fuel_start=100.0, fuel_end=94.0, fuel_used=6.0, position=1,
        is_pit_lap=False, is_out_lap=False))
    store.close()
    return path, event_id


def _has_mcp() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _has_mcp(), reason="the mcp package is not installed")


def test_it_serves_the_events_it_has(seeded):
    db, _event_id = seeded
    got = call("list_events", db=db)
    assert len(got) == 1
    assert got[0]["car_name"] == "Porsche 911 RSR (991) '17"
    assert got[0]["game_version"] == "1.71"


def test_a_sheet_comes_back_with_its_shift_table(seeded):
    db, _ = seeded
    got = call("setup_sheets", {"car_name": "Porsche 911 RSR (991) '17"}, db=db)
    assert got[0]["values"]["rh_f"] == 60
    assert got[0]["shiftRpm"] == {"1": 7400.0}


def test_missing_slider_ranges_say_so_rather_than_return_nothing(seeded):
    """A car with no measured ranges is a fact about the car, and reasoning in
    percent of range is only safe where they exist."""
    db, _ = seeded
    got = call("slider_ranges", {"car_name": "Porsche 911 RSR (991) '17"}, db=db)
    assert got["found"] is False and "percent of range" in got["note"]


def test_proposing_a_sheet_files_it_and_changes_nothing(seeded):
    """**The discipline.** It lands in the prompt log for review; the stored
    sheet is untouched, because only the driver knows what went into the car."""
    from pitcrew.store.db import Store

    db, event_id = seeded
    got = call("propose_setup_sheet",
               {"event_id": event_id, "reply": "rh_f: 999\nrh_r: 999"}, db=db)
    assert got["filed"] is True and got["promptId"]

    store = Store(db)
    try:
        sheet = store.sheet_for("Porsche 911 RSR (991) '17", "race")
        assert sheet.values["rh_f"] == 60, "the proposal became the sheet"
        assert store.get_prompt(got["promptId"])["reply"]
    finally:
        store.close()


def test_a_proposed_plan_is_saved_unapproved(seeded):
    """Nothing arms a plan that has not been approved in the app."""
    from pitcrew.store.db import Store

    db, event_id = seeded
    got = call("propose_strategy",
               {"event_id": event_id, "plan": json.dumps({"stints": [10, 10]})},
               db=db)
    assert got["saved"] is True and got["approved"] is False

    store = Store(db)
    try:
        assert store.get_approved_strategy(event_id) is None
    finally:
        store.close()


def test_a_plan_that_is_not_json_is_refused_rather_than_stored(seeded):
    db, event_id = seeded
    got = call("propose_strategy", {"event_id": event_id, "plan": "{nope"},
               db=db)
    assert got["saved"] is False and "not JSON" in got["error"]
