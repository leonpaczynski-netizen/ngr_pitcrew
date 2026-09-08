"""**A table with no writer is worse than no table.**

This codebase has built both ends of a feature and skipped the caller five
times. So this file is constraint 2 of the 8 Sep brief made executable: the
MCP tools exist, a client can reach them over real stdio, and a round trip
through them lands a row in the database and reads it back out.

It is deliberately the same shape as `test_mcp_server.py` — a real subprocess,
a real client session, a throwaway database named by `PITCREW_DB` — because a
tool that only works when called as a Python function is not reachable by the
thing that needs it.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

CAR = "Lamborghini Huracan GT3 '15"
CIRCUIT = "daytona-international-speedway-road-course"


def call(tool: str, args: dict | None = None, *, db: str) -> dict | list:
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
def db(tmp_path) -> str:
    """An empty throwaway file. **Never the live database.**

    `PITCREW_DATA_DIR` does nothing and a bare `Store()` opens
    `data/pitcrew.db`, which is 96 sessions of laps with `lap_frames`
    cascading off them.
    """
    return str(tmp_path / "pitcrew.db")


def test_the_tools_are_listed(db):
    """Present in the manifest, not just importable."""
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
                return {t.name for t in (await session.list_tools()).tools}

    names = asyncio.run(run())
    assert {"write_measurement", "write_verdict", "measurements",
            "axis_status"} <= names


def test_a_measurement_written_over_mcp_comes_back_out(db):
    """The round trip. This is the caller existing, end to end."""
    written = call("write_measurement", {
        "car_name": CAR, "metric": "on_power_rotation_index", "value": 0.00788,
        "unit": "ratio", "scope": "corner", "source": "DERIVED",
        "circuit_key": CIRCUIT, "zone": "T5 exit",
        "config_ref": "huracan-daytona#s143", "config_label": "A",
        "n": 15, "n_basis": "clean laps", "noise_floor": 0.00104,
        "floor_method": "odd/even split of one session's clean laps",
        "session_ids": [143], "game_version": "1.71",
        "measured_on": "2026-09-07"}, db=db)
    assert written["written"] is True, written
    row_id = written["measurementId"]

    back = call("measurements", {"car_name": CAR, "metric":
                                 "on_power_rotation_index"}, db=db)
    assert len(back) == 1
    assert back[0]["id"] == row_id
    assert back[0]["value"] == 0.00788
    assert back[0]["noiseFloor"] == 0.00104
    assert back[0]["sessionIds"] == [143]

    # And the store API sees the same row the tool wrote — one table, one
    # writer, not two paths that happen to agree.
    from pitcrew.store.db import Store

    store = Store(db)
    try:
        rows = store.measurements(car_name=CAR)
        assert [r.id for r in rows] == [row_id]
        assert rows[0].config_ref == "huracan-daytona#s143"
    finally:
        store.close()


def test_a_measurement_with_no_floor_stays_null_through_the_seam(db):
    """Rule 3 across the wire, where a default is most likely to creep in."""
    call("write_measurement", {
        "car_name": CAR, "metric": "front_scrub_t5_exit", "value": 0.0099,
        "unit": "ratio", "scope": "corner", "source": "DERIVED",
        "circuit_key": CIRCUIT, "zone": "T5 exit"}, db=db)
    back = call("measurements", {"metric": "front_scrub_t5_exit"}, db=db)
    assert back[0]["noiseFloor"] is None
    # `n` was not given either, and 0 is not a sample count.
    assert back[0]["n"] is None


def test_the_seam_refuses_a_zero_floor_rather_than_storing_it(db):
    got = call("write_measurement", {
        "car_name": CAR, "metric": "m", "value": 1.0, "unit": "ratio",
        "scope": "lap", "source": "DERIVED", "noise_floor": 0.0}, db=db)
    assert got["written"] is False
    assert "noise floor of 0.0" in got["error"]
    assert call("measurements", {}, db=db) == []


def test_the_seam_refuses_a_setup_value_in_the_config_reference(db):
    """⛔ The one-copy rule, enforced at the door the engineer writes through."""
    got = call("write_measurement", {
        "car_name": CAR, "metric": "m", "value": 1.0, "unit": "ratio",
        "scope": "lap", "source": "DERIVED",
        "config_ref": "rh_r=64 lsd_a 14"}, db=db)
    assert got["written"] is False
    assert "slider value" in got["error"]


def test_a_verdict_round_trips_and_untested_is_the_default(db):
    """**The question that had no answer on 8 Sep, asked over the wire.**"""
    board = call("axis_status", {"car_name": CAR, "circuit_key": CIRCUIT},
                 db=db)
    assert "rh_r" in board["untested"]
    assert board["settled"] == {}

    got = call("write_verdict", {
        "car_name": CAR, "axis": "lsd_a", "verdict": "refuted",
        "direction": "down", "circuit_key": CIRCUIT,
        "instrument": "on_power_rotation_index", "instrument_floor": 0.00104,
        "decided_on": "2026-09-08", "game_version": "1.71",
        "why": "less acceleration lock gave less rotation on power"}, db=db)
    assert got["written"] is True, got

    one = call("axis_status", {"car_name": CAR, "circuit_key": CIRCUIT,
                               "axis": "lsd_a"}, db=db)
    assert one["current"]["verdict"] == "refuted"
    assert one["current"]["instrument"] == "on_power_rotation_index"
    assert one["current"]["instrumentFloor"] == 0.00104

    board = call("axis_status", {"car_name": CAR, "circuit_key": CIRCUIT},
                 db=db)
    assert board["settled"] == {"lsd_a": "refuted"}
    assert "lsd_a" not in board["untested"]
    # Still untested is still the answer for everything else.
    assert "rh_f" in board["untested"]


def test_the_seam_refuses_a_refutation_that_names_no_instrument(db):
    """A channel that cannot see the change never refuted the lever."""
    got = call("write_verdict", {
        "car_name": CAR, "axis": "lsd_a", "verdict": "refuted",
        "direction": "down", "circuit_key": CIRCUIT,
        "why": "it felt worse"}, db=db)
    assert got["written"] is False
    assert "instrument" in got["error"]


def test_every_write_is_recorded_in_the_audit_trail(db):
    """The same rule as the other authoritative writes: nothing lands silently."""
    call("write_measurement", {
        "car_name": CAR, "metric": "dynamic_rake", "value": 10.51,
        "unit": "mm", "scope": "session", "source": "DERIVED",
        "circuit_key": CIRCUIT}, db=db)
    call("write_verdict", {
        "car_name": CAR, "axis": "rh_r", "verdict": "unresolvable",
        "circuit_key": CIRCUIT, "instrument": "on_power_rotation_index",
        "instrument_floor": 0.00104, "why": "inside the floor"}, db=db)

    written = call("engineer_writes", {}, db=db)
    kinds = {row["kind"] for row in written}
    assert {"measurement", "verdict"} <= kinds
