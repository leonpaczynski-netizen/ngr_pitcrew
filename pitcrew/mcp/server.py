"""The seam between the tuning brain and the app, without a clipboard.

Pit Crew has always fed a race-engineering knowledge base by having the driver
copy a payload out of the app and paste it into a conversation. The contract
that payload obeys is right and is not changing - `EXPORT-CONTRACT.md` is still
the shape. **What changes here is the clipboard, not the contract.**

### What it may and may not do

**Reads are open. Writes propose; they never apply.**

`CLAUDE.md` §4.1 makes the driver's report primary evidence, and §7 would
rather refuse than emit something wrong. A model that could write a setup sheet
straight into the store would be deciding what was in the car, which is the one
thing only he knows - and the 17 Aug audit is what that costs: the app reported
a sheet the car was not running for three sessions out of three, and would have
produced a completely coherent diagnosis of a car that was not on the circuit.

So the two write tools land where the app already has an approval step:

* `propose_strategy` writes an **unapproved** row. `Store.approve_strategy` is
  a separate call the app makes when he says so, and nothing arms a plan that
  has not been through it.
* `propose_setup_sheet` files the reply into the **prompt log**, which is where
  a pasted reply goes today. He reads it and applies it on the Event screen,
  exactly as now.

Neither one can put a number under a lap.

### Running it

    python -m pitcrew.mcp.server

Speaks stdio, so it is launched by the client rather than left listening. One
store connection, opened per call and closed, so it can never hold a lock the
app wants during a session.
"""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer

from pitcrew.export.build import build_event_export, drivetrain_of
from pitcrew.setup.parse import parse_reply
from pitcrew.store.db import Store

mcp = MCPServer("pitcrew")

# Enough to answer a question, few enough that the reply is readable. A tool
# that returns four hundred laps has answered nothing.
MAX_ROWS = 60


def _dump(value) -> str:
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


def _store() -> Store:
    """A store, closed by every caller.

    `PITCREW_DB` points it somewhere else - at a throwaway database under test,
    or at a second checkout. Unset, it opens the one the app uses.
    """
    path = os.environ.get("PITCREW_DB")
    return Store(path) if path else Store()


# --------------------------------------------------------------------- reads

@mcp.tool()
def list_events() -> str:
    """Every event on file: car, circuit, format, multipliers, game version."""
    store = _store()
    try:
        keep = ("id", "name", "track", "layout", "car_name", "race_type",
                "race_laps", "race_minutes", "tyre_wear_mult", "fuel_mult",
                "game_version", "abs_setting", "tcs", "drivetrain")
        return _dump([{k: e.get(k) for k in keep} for e in store.list_events()])
    finally:
        store.close()


@mcp.tool()
def setup_sheets(car_name: str) -> str:
    """Every stored sheet for a car, newest first, with its shift table."""
    store = _store()
    try:
        out = []
        for sheet in store.list_setup_sheets(car_name):
            out.append({"id": sheet.id, "name": sheet.sheet_name,
                        "purpose": sheet.purpose, "values": sheet.values,
                        "gears": sheet.gears, "shiftRpm": sheet.shift_rpm,
                        "notes": sheet.notes})
        return _dump(out)
    finally:
        store.close()


@mcp.tool()
def slider_ranges(car_name: str) -> str:
    """The car's measured slider limits, and the version they were read on.

    **1.71 moved adjustment ranges**, and percent-of-range silently changes
    meaning when a range moves - the three LSD axes went from a shared 5-60 to
    0-30, 0-100 and 0-99, so one absolute value now means three different
    proportions. A record read on an older version says so here.
    """
    store = _store()
    try:
        record = store.get_range_record(car_name)
        if record is None:
            return _dump({"found": False, "car": car_name,
                          "note": "no ranges measured for this car - reason in "
                                  "percent of range only where they exist"})
        return _dump({"found": True, "car": car_name,
                      "measured": record.measured_date,
                      "gameVersion": record.game_version,
                      "verified": record.verified, "ranges": record.ranges})
    finally:
        store.close()


@mcp.tool()
def event_export(event_id: int, kind: str = "practice") -> str:
    """The full `gt7-pitcrew` payload for an event - the contract's own shape.

    Refuses an event whose sessions straddle a physics update, because
    pre- and post-patch laps are not one body of evidence about one car.
    """
    store = _store()
    try:
        return _dump(build_event_export(store, event_id, kind=kind))
    except ValueError as exc:
        return _dump({"refused": str(exc)})
    finally:
        store.close()


@mcp.tool()
def laps(event_id: int, kind: str = "practice") -> str:
    """Counted laps for an event: time, fuel, compound, wear, exclusions."""
    store = _store()
    try:
        rows = store.list_event_laps(event_id, kind)[:MAX_ROWS]
        keep = ("lap_num", "lap_time_ms", "fuel_start", "fuel_end", "compound",
                "fuel_map", "excluded", "exclusion_reason",
                "wear_fl", "wear_fr", "wear_rl", "wear_rr", "game_version")
        return _dump([{k: r.get(k) for k in keep} for r in rows])
    finally:
        store.close()


@mcp.tool()
def strategy_evidence(event_id: int) -> str:
    """What a plan for this event would be built on, and how firm each part is.

    Every row carries its source - measured, declared, assumed or missing - so
    a figure the app derived is never mistaken for one somebody took.
    """
    from pitcrew.strategy.evidence import build_inputs

    store = _store()
    try:
        _inputs, evidence = build_inputs(store, event_id)
        return _dump([{"label": e.label, "value": e.value, "source": e.source,
                       "note": e.note} for e in evidence])
    except ValueError as exc:
        return _dump({"refused": str(exc)})
    finally:
        store.close()


@mcp.tool()
def car_context(event_id: int) -> str:
    """Drivetrain and where it came from - declared, or the catalogue."""
    store = _store()
    try:
        event = store.get_event(event_id)
        if event is None:
            return _dump({"found": False})
        value, source = drivetrain_of(store, event)
        return _dump({"car": event.get("car_name"), "drivetrain": value,
                      "drivetrainSource": source,
                      "gameVersion": event.get("game_version")})
    finally:
        store.close()


@mcp.tool()
def prompt_log(event_id: int | None = None) -> str:
    """Which prompts were sent and which replies came back."""
    store = _store()
    try:
        rows = store.list_prompts(event_id)[:MAX_ROWS]
        keep = ("id", "kind", "prompt_version", "app_version", "created_at",
                "event_id")
        return _dump([{k: r.get(k) for k in keep} | {
            "hasReply": bool(r.get("reply"))} for r in rows])
    finally:
        store.close()


# ------------------------------------------------------------------- writes
# Both propose. Neither applies.

@mcp.tool()
def propose_setup_sheet(event_id: int, reply: str) -> str:
    """File a setup reply for the driver to review and apply himself.

    **It does not become the sheet.** It lands in the prompt log, which is
    where a pasted reply goes today, and he applies it on the Event screen. The
    app has been wrong about which sheet was in the car three sessions out of
    three; a tool that wrote one directly would make that unrecoverable.

    The reply is parsed here only to report what was understood - anything not
    recognised comes back in `unmatched` rather than being dropped.
    """
    store = _store()
    try:
        parsed = parse_reply(reply)
        issue_id = store.log_prompt(
            kind="refinement", body="(proposed over MCP)",
            prompt_version="mcp", app_version="mcp", event_id=event_id)
        store.save_prompt_reply(issue_id, reply)
        race = getattr(parsed, "race", None) or getattr(parsed, "sheet", None)
        return _dump({
            "filed": True, "promptId": issue_id,
            "note": "filed for review - apply it on the Event screen. Nothing "
                    "has changed in the car or in the app's record of it.",
            "understood": getattr(race, "values", None),
            "unmatched": list(getattr(parsed, "unmatched", []) or [])[:20],
        })
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"filed": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def propose_strategy(event_id: int, plan: str, label: str = "") -> str:
    """Save a race plan as a candidate. It is not approved and cannot be armed.

    `plan` is the JSON of a plan. Approval is a separate act the driver takes
    in the app, and the coordinator will not arm anything that has not been
    through it.
    """
    store = _store()
    try:
        payload = json.loads(plan) if isinstance(plan, str) else plan
    except json.JSONDecodeError as exc:
        return _dump({"saved": False, "error": f"plan is not JSON: {exc}"})
    try:
        strategy_id = store.save_strategy(event_id, payload,
                                          label=label or "proposed over MCP")
        return _dump({"saved": True, "strategyId": strategy_id,
                      "approved": False,
                      "note": "saved as a candidate. It has to be approved in "
                              "the app before anything can arm it."})
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"saved": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
