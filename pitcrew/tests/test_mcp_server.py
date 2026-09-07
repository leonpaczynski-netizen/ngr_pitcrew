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
    """A database with one event, one shift table and one lap, on disk."""
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.store.db import Store
    from pitcrew.telemetry.session_state import Lap

    path = str(tmp_path / "pitcrew.db")
    store = Store(path)
    event_id = store.create_event(
        name="Monza", track="Autodromo Nazionale Monza", layout="Full",
        car_name="Porsche 911 RSR (991) '17", race_type="laps", race_laps=20,
        tyre_wear_mult="8x", fuel_mult="3x", game_version="1.71")
    store.save_shift_points(ShiftPoints(
        car_name="Porsche 911 RSR (991) '17", circuit_key="monza",
        performance={1: 7400.0}, fuel_saving={1: 6800.0}))
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


def test_a_shift_table_comes_back_for_the_circuit_it_was_issued_for(seeded):
    db, _ = seeded
    got = call("shift_points",
               {"car_name": "Porsche 911 RSR (991) '17",
                "circuit_key": "monza"}, db=db)
    assert got["performanceRpm"] == {"1": 7400.0}
    assert got["fuelSavingRpm"] == {"1": 6800.0}

    elsewhere = call("shift_points",
                     {"car_name": "Porsche 911 RSR (991) '17",
                      "circuit_key": "spa"}, db=db)
    assert elsewhere is None, "a gearbox is cut for the circuit"


def test_issuing_a_swapped_pair_of_columns_is_refused(seeded):
    """A fuel-saving point above its own performance point is silent at the
    wheel and costs fuel in the direction he was told it saved."""
    db, _ = seeded
    got = call("write_shift_points",
               {"car_name": "A", "circuit_key": "monza",
                "performance_rpm": {"3": 8000},
                "fuel_saving_rpm": {"3": 8400}}, db=db)
    assert got["written"] is False
    assert "not below performance" in got["error"]


def test_missing_slider_ranges_say_so_rather_than_return_nothing(seeded):
    """A car with no measured ranges is a fact about the car, and reasoning in
    percent of range is only safe where they exist."""
    db, _ = seeded
    got = call("slider_ranges", {"car_name": "Porsche 911 RSR (991) '17"}, db=db)
    assert got["found"] is False and "percent of range" in got["note"]


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


def test_a_proposed_plan_is_read_as_whole_numbers(seeded):
    """**This tool stored whatever JSON arrived.** `write_strategy` goes
    through `from_dict`, which reads a plan's counts once - JSON has no
    integer type, so a desk writing `11` may send `11.0`, and six readers had
    been taught that one at a time while the plan kept the float. George then
    said "the next 9.0-lap stint" with the hose in.
    """
    from pitcrew.store.db import Store

    db, event_id = seeded
    got = call("propose_strategy",
               {"event_id": event_id,
                "plan": json.dumps({
                    "stints": [{"laps": 10.0, "compound": "RS",
                                "start_lap": 1.0},
                               {"laps": 10.0, "compound": "RS",
                                "start_lap": 11.0}],
                    "stops": 1.0, "pit_laps": [10.0]})},
               db=db)
    assert got["saved"] is True

    store = Store(db)
    try:
        row = next(r for r in store.list_strategies(event_id)
                   if r["id"] == got["strategyId"])
    finally:
        store.close()
    plan = row["plan"]
    assert plan["stops"] == 1 and not isinstance(plan["stops"], float)
    assert plan["pit_laps"] == [10]
    for stint in plan["stints"]:
        for key in ("laps", "start_lap"):
            assert isinstance(stint[key], int), (key, stint[key])
    # The expression the coordinator arms from.
    first = plan["stints"][0]
    assert isinstance(first["start_lap"] + first["laps"] - 1, int)


def test_a_proposed_plan_carrying_the_apps_own_keys_is_refused(seeded):
    """`export` is the section the app builds and `_strategy_section` prefers
    a stored one verbatim, so a desk-supplied block shipped its own figures
    into the contract. The desk's own keys are refused too - with the tool
    that takes them, because renaming a `playbook` would strip George's
    bounds rather than fix anything."""
    db, event_id = seeded
    for key in ("export", "handover", "playbook"):
        got = call("propose_strategy",
                   {"event_id": event_id,
                    "plan": json.dumps({"stints": [{"laps": 10}], key: {}})},
                   db=db)
        assert got["saved"] is False, (key, got)
        assert key in got["error"], got
    # **The answer is per key, because the set holds three ownerships.**
    # `write_strategy` takes the desk's; it REFUSES `export` too, so naming
    # it there would be wrong advice; and `unhandled`/`certificate` are
    # worked out by the app wherever they arrive.
    for key, expected in (("playbook", "use write_strategy"),
                          ("author", "use write_strategy"),
                          ("export", "the app builds that section itself"),
                          ("unhandled", "the app works that out"),
                          ("certificate", "the app works that out")):
        got = call("propose_strategy",
                   {"event_id": event_id,
                    "plan": json.dumps({"stints": [{"laps": 10}], key: {}})},
                   db=db)
        assert expected in got["error"], (key, got)

    # A mixed payload answers each key on its own terms.
    mixed = call("propose_strategy",
                 {"event_id": event_id,
                  "plan": json.dumps({"stints": [{"laps": 10}],
                                      "export": {}, "playbook": []})},
                 db=db)
    assert "use write_strategy" in mixed["error"], mixed
    assert "the app builds that section itself" in mixed["error"], mixed

    # And a plan that is not a JSON object is refused rather than indexed.
    said = call("propose_strategy",
                {"event_id": event_id, "plan": json.dumps([1, 2])}, db=db)
    assert said["saved"] is False and "JSON object" in said["error"], said


def test_a_proposed_plan_is_stamped_so_it_can_actually_be_run(seeded):
    """**The door was hardened for counts and nobody asked what it STORES.**

    `write_strategy` stamps; this one did not, and `approve_stored_strategy`
    only certifies while `start_race` arms straight off the row. So a
    proposed plan approved in the app had no `start_lap` - every stint then
    ends at `laps`, because `_apply_stint` reads `start_lap or 1` - so two
    stints of a three-stint plan share a box lap and `_box_now` fires every
    lap to the flag. That is the nine-box-calls defect `_with_start_laps`
    exists to prevent. No `context` either, so `arm` skips
    `planned.matches(actual)` and a plan for one circuit arms at another.
    """
    from pitcrew.store.db import Store

    db, event_id = seeded
    got = call("propose_strategy",
               {"event_id": event_id,
                "plan": json.dumps({"stints": [
                    {"laps": 10, "compound": "RS"},
                    {"laps": 10, "compound": "RS"},
                    {"laps": 10, "compound": "RS"}]})},
               db=db)
    assert got["saved"] is True, got

    store = Store(db)
    try:
        row = next(r for r in store.list_strategies(event_id)
                   if r["id"] == got["strategyId"])
    finally:
        store.close()
    plan = row["plan"]
    assert [s["start_lap"] for s in plan["stints"]] == [1, 11, 21], plan
    assert plan.get("context"), "no context: a plan arms at any circuit"
    # And the box laps are distinct, which is what the defect destroyed.
    ends = [s["start_lap"] + s["laps"] - 1 for s in plan["stints"]]
    assert len(set(ends)) == len(ends), ends


def test_a_start_lap_that_is_not_a_whole_lap_is_refused(seeded):
    """`stint_ends_on_lap` is `start_lap + laps - 1`, and nothing checked the
    start: `1.5` passed both doors and the gate, and George said "Box in 8.5
    laps." The door reads what it can; this is the place that refuses what it
    cannot."""
    from pitcrew.strategy.certify import certify
    from pitcrew.strategy.model import RaceInputs

    from .test_certify import inputs, plan, stint

    ok = plan(stint(10), stint(10, "RM"))
    assert certify(ok, inputs()).certified

    half = {**ok, "stints": [{**ok["stints"][0], "start_lap": 1.5},
                             ok["stints"][1]]}
    got = certify(half, inputs())
    assert not got.certified
    assert any("whole one" in r for r in got.refusals), got.refusals
    assert isinstance(RaceInputs, type)


def test_a_plan_that_is_not_json_is_refused_rather_than_stored(seeded):
    db, event_id = seeded
    got = call("propose_strategy", {"event_id": event_id, "plan": "{nope"},
               db=db)
    assert got["saved"] is False and "not JSON" in got["error"]
