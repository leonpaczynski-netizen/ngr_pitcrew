"""The seam between the tuning brain and the app, without a clipboard.

Pit Crew has always fed a race-engineering knowledge base by having the driver
copy a payload out of the app and paste it into a conversation. The contract
that payload obeys is right and is not changing - `EXPORT-CONTRACT.md` is still
the shape. **What changes here is the clipboard, not the contract.**

### What it may and may not do

**Reads are open. Writes apply, and every one of them is recorded.**

⚠ **This reverses what this file said until 29 Aug 2026**, and the reversal is
the driver's decision, taken in a design interview on that date. The old rule
was *"writes propose; they never apply"*, and its reason was good: the app had
been wrong about which sheet was in the car three sessions out of three, so a
tool that wrote one directly would make that unrecoverable.

What changed is that **the database is now the single source of truth for the
app and for the race engineer both**. A correction that lives in a
conversation leaves 96 sessions of history wrong and the export still shipping
a sheet the car was not running - which is the same defect the old rule was
protecting against, arriving by the other road.

So the writes apply, and `unrecoverable` is the word that had to stop being
true:

* `write_setup_sheet` lands in `setup_sheets` and the session re-binds. **Every
  write records the row it replaced, in full** (`engineer_writes`), and
  `undo_setup_sheet` puts it back. That table is also the only record of who
  changed the car and when - without it a sheet written from outside is
  indistinguishable from one the driver typed himself.
* `write_strategy` writes an **approved** plan, but `certify.py` has to pass or
  it cannot arm. A sheet describes something that already exists; a plan is an
  instruction that will be executed under a helmet, and the failure on record
  is a plan priced 50 s slower than its own alternative that certified as fine.
  A plan is never undone - it may already be armed and partly executed - it is
  replaced by writing a better one.
* `write_race_knowledge` writes the briefing George's rules read.

`propose_setup_sheet` and `propose_strategy` remain, unchanged, for a reply he
wants to read before it touches anything.

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
        from pitcrew.strategy.certify import certify_for_event

        certificate = certify_for_event(store, event_id, payload)
        strategy_id = store.save_strategy(
            event_id, payload,
            label=label or "proposed over MCP",
            evidence={"certified": certificate.certified,
                      "refusals": certificate.refusals,
                      "warnings": certificate.warnings,
                      "unchecked": certificate.unchecked})
        return _dump({
            "saved": True, "strategyId": strategy_id, "approved": False,
            "certified": certificate.certified,
            "refusals": certificate.refusals,
            "warnings": certificate.warnings,
            "unchecked": certificate.unchecked,
            "verdict": certificate.describe(),
            "note": ("saved as a candidate. It has to be approved in the app "
                     "before anything can arm it"
                     + ("" if certificate.certified else
                        " - and as it stands the car cannot execute it")),
        })
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"saved": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


# ------------------------------------------------- authoritative writes ⚠
#
# See the module docstring for why these exist and what makes them safe. Every
# one records what it replaced; the sheet write can be undone.

@mcp.tool()
def write_setup_sheet(car_name: str, reply: str, purpose: str = "race",
                      circuit_key: str = "", event_id: int = 0) -> str:
    """Write a setup sheet straight into the app's record of the car. ⚠

    **This changes what the app believes is bolted to the car**, which is rank
    zero of every diagnosis. Use it when the sheet has actually been typed into
    GT7; use `propose_setup_sheet` when it is a suggestion he should read first.

    The previous sheet is recorded in full before it is replaced, so
    `undo_setup_sheet` can put it back, and `engineer_writes` is the record of
    who changed it and when.
    """
    store = _store()
    try:
        parsed = parse_reply(reply)
        race = getattr(parsed, "race", None) or getattr(parsed, "sheet", None)
        if race is None or not getattr(race, "values", None):
            return _dump({
                "written": False,
                "error": "nothing in that reply parsed as a setup sheet",
                "unmatched": list(getattr(parsed, "unmatched", []) or [])[:20]})

        key = circuit_key or None
        before = store.sheet_for(car_name, purpose, key)
        sheet = _sheet_from(race, car_name, purpose, key)
        sheet_id = store.save_setup_sheet(sheet)
        store.note_engineer_write(
            "setup_sheet", target_id=sheet_id,
            event_id=event_id or None, author="race engineer (MCP)",
            summary=f"wrote {sheet.sheet_name!r} for {car_name}"
                    + (f" at {key}" if key else ""),
            before=_as_dict(before), after=_as_dict(sheet))
        return _dump({
            "written": True, "sheetId": sheet_id,
            "values": getattr(race, "values", None),
            "unmatched": list(getattr(parsed, "unmatched", []) or [])[:20],
            "note": "this is now the app's record of what is in the car. "
                    "`undo_setup_sheet` puts the previous one back.",
        })
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def undo_setup_sheet(write_id: int = 0) -> str:
    """Put back the sheet an authoritative write replaced.

    With no `write_id`, undoes the most recent sheet write that has not already
    been undone. Returns what it did, in words.
    """
    store = _store()
    try:
        if not write_id:
            recent = [row for row in store.list_engineer_writes(
                kind="setup_sheet", limit=20) if not row["undone_at"]]
            if not recent:
                return _dump({"undone": False,
                              "error": "no sheet write left to undo"})
            write_id = recent[0]["id"]
        return _dump({"undone": True, "writeId": write_id,
                      "result": store.undo_engineer_write(write_id)})
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"undone": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def write_strategy(event_id: int, plan: str, label: str = "") -> str:
    """Write an APPROVED race plan. It still cannot arm unless it certifies. ⚠

    A sheet describes something that already exists; a plan is an instruction
    that will be executed under a helmet. So this is the one authoritative
    write with a machine check in front of it - `certify.py` prices the plan
    against the evidence, and a plan that fails is stored as a candidate rather
    than approved, because the failure on record is a plan priced 50 s slower
    than its own alternative.

    Never undone. It may already be armed and partly executed; a plan is
    replaced by writing a better one.
    """
    store = _store()
    try:
        payload = json.loads(plan) if isinstance(plan, str) else plan
    except json.JSONDecodeError as exc:
        return _dump({"written": False, "error": f"plan is not JSON: {exc}"})
    try:
        from pitcrew.strategy.certify import certify_for_event
        from pitcrew.strategy.execution import stamp

        payload = stamp(store, event_id, payload)
        certificate = certify_for_event(store, event_id, payload)
        strategy_id = store.save_strategy(
            event_id, payload, label=label or "written by the race engineer",
            evidence={"certified": certificate.certified,
                      "refusals": certificate.refusals,
                      "warnings": certificate.warnings,
                      "unchecked": certificate.unchecked},
            status="candidate")
        if certificate.certified:
            store.approve_strategy(strategy_id)
        store.note_engineer_write(
            "strategy", target_id=strategy_id, event_id=event_id,
            author="race engineer (MCP)",
            summary=("approved" if certificate.certified
                     else "stored as a candidate - it did not certify"),
            after={"label": label, "certified": certificate.certified})
        return _dump({
            "written": True, "strategyId": strategy_id,
            "approved": certificate.certified,
            "certified": certificate.certified,
            "refusals": certificate.refusals,
            "warnings": certificate.warnings,
            "unchecked": certificate.unchecked,
            "verdict": certificate.describe(),
            "note": ("approved and ready to arm." if certificate.certified else
                     "NOT approved: it did not certify, so the car cannot "
                     "execute it as written. Fix the refusals and write again."),
        })
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def write_race_knowledge(circuit_key: str, briefing: str,
                         event_id: int = 0) -> str:
    """Write the briefing George's rules read during the race.

    `briefing` is JSON with any of: `pit_loss_s`, `refuel_l_per_s`,
    `undercut_s`, `overcut_s`, `expected_constraint`, `constraint_watch`,
    `rivals`, `tow_s_per_lap`, `calls_off`, `notes`.

    `event_id` 0 writes the circuit's own record - the track constants, which
    every round here inherits. A real event id writes that race's, and the two
    are merged field by field with the race's winning.

    **`calls_off` is checked before anything is stored.** It names calls George
    will not make, and a typo there is a call that quietly never happens.
    """
    store = _store()
    try:
        payload = json.loads(briefing) if isinstance(briefing, str) else briefing
    except json.JSONDecodeError as exc:
        return _dump({"written": False, "error": f"briefing is not JSON: {exc}"})
    try:
        from dataclasses import replace

        from pitcrew.race.knowledge import Knowledge

        base = store.get_race_knowledge(circuit_key, event_id or None)
        base = base or Knowledge(circuit_key=circuit_key,
                                 event_id=event_id or None)
        fields = {key: value for key, value in payload.items()
                  if key in Knowledge.__dataclass_fields__}
        for key in ("rivals", "calls_off"):
            if key in fields:
                fields[key] = tuple(fields[key] or ())
        written = replace(base, circuit_key=circuit_key,
                          event_id=event_id or None,
                          author="race engineer (MCP)", **fields)
        store.save_race_knowledge(written)
        store.note_engineer_write(
            "knowledge", event_id=event_id or None,
            author="race engineer (MCP)",
            summary=f"briefing for {circuit_key}",
            before=base.as_export(), after=written.as_export())
        return _dump({"written": True, "briefing": written.as_export(),
                      "ignored": sorted(set(payload) - set(fields))})
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def engineer_writes(kind: str = "", limit: int = 20) -> str:
    """What has been written into the app from outside, newest first.

    The audit trail the authoritative writes exist behind. Without it a sheet
    written from here is indistinguishable from one the driver typed himself.
    """
    store = _store()
    try:
        return _dump(store.list_engineer_writes(kind=kind or None,
                                                limit=min(limit, MAX_ROWS)))
    finally:
        store.close()


def _sheet_from(race, car_name: str, purpose: str, circuit_key: str | None):
    """A parsed reply as a `SetupSheet` bound to this car and circuit."""
    from pitcrew.setup.sheet import SetupSheet

    return SetupSheet(
        car_name=car_name,
        sheet_name=getattr(race, "sheet_name", None) or "written by the engineer",
        values=dict(getattr(race, "values", None) or {}),
        gears=list(getattr(race, "gears", None) or []),
        purpose=purpose,
        circuit_key=circuit_key)


def _as_dict(sheet):
    """A `SetupSheet` as plain JSON for the audit trail, or None."""
    if sheet is None:
        return None
    from dataclasses import asdict

    return asdict(sheet)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
