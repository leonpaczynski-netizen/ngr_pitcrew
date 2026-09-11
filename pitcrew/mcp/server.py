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

* `write_shift_points` lands in `shift_points` and the beep uses it from the
  next session. **The app no longer holds a setup sheet at all** - the tune
  builder holds the car and the gearbox, and the driver confirms what is in
  it against GT7's own settings screen. The upshift table is the exception,
  and only because it has to reach a speaker at 60 Hz: it is issued with the
  setup it belongs to, and nobody types it in by hand.
* `write_strategy` writes an **approved** plan, but `certify.py` has to pass or
  it cannot arm. A sheet describes something that already exists; a plan is an
  instruction that will be executed under a helmet, and the failure on record
  is a plan priced 50 s slower than its own alternative that certified as fine.
  A plan is never undone - it may already be armed and partly executed - it is
  replaced by writing a better one.
* `write_race_knowledge` writes the briefing George's rules read.
* `write_measurement` and `write_verdict` land the numbers the engineer
  derives off the frames, and what an axis is believed to do on the strength
  of them. They apply for the same reason as the rest: a number that lives
  only in a conversation is re-derived from scratch next session and cannot
  be compared with itself. Neither holds a setup value - a measurement points
  at its configuration by reference, and `brain/car-state/<car>-<circuit>.md`
  stays the only place one is written down.

`propose_strategy` remains, unchanged, for a plan he wants to read before it
touches anything.

### Running it

    python -m pitcrew.mcp.server

Speaks stdio, so it is launched by the client rather than left listening. One
store connection, opened per call and closed, so it can never hold a lock the
app wants during a session.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

from mcp.server.mcpserver import MCPServer

from pitcrew.engineer.shift_points import ShiftPoints
from pitcrew.export.build import build_event_export, drivetrain_of
from pitcrew.store.db import Store

mcp = MCPServer("pitcrew")

# Enough to answer a question, few enough that the reply is readable. A tool
# that returns four hundred laps has answered nothing.
MAX_ROWS = 60


def _today() -> str:
    return _dt.date.today().isoformat()


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
        # The regulations that bind a sheet travel with the event (plan row
        # 2.7): `initial` reads BoP and the limits here instead of asking.
        keep = ("id", "name", "track", "layout", "car_name", "race_type",
                "race_laps", "race_minutes", "tyre_wear_mult", "fuel_mult",
                "game_version", "abs_setting", "tcs", "drivetrain",
                "bop_enabled", "tuning_allowed", "power_limit_bhp",
                "weight_limit_kg", "series")
        return _dump([{k: e.get(k) for k in keep} for e in store.list_events()])
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
        from pitcrew.strategy.handover import RESERVED_KEYS, whole_numbers

        # **The other door goes through `from_dict`; this one stored whatever
        # arrived.** So the two things that door does - reading JSON numbers
        # as counts, and refusing the keys the app owns - both had a way
        # round them here, on the tool whose docstring says it takes "the
        # JSON of a plan". `export` is the one that matters: a desk-supplied
        # block is preferred verbatim over the section the app builds.
        if not isinstance(payload, dict):
            return _dump({"saved": False,
                          "error": "plan must be a JSON object"})
        # **Three ownerships in one set, so the answer is per key.**
        # `export` is the app's own section, and `write_strategy` refuses it
        # too - so "use the other tool" is wrong advice for it. `handover`,
        # `author` and `playbook` are the desk's and that tool does take
        # them. `unhandled` and `certificate` are recomputed by the app and
        # dropped wherever they arrive, so naming another tool would be
        # wrong for those as well.
        TAKEN = ("handover", "author", "playbook")
        clash = sorted(RESERVED_KEYS & set(payload))
        if clash:
            said = []
            for key in clash:
                if key in TAKEN:
                    said.append(f"{key!r} - use write_strategy, which takes "
                                f"it")
                elif key == "export":
                    said.append(f"{key!r} - the app builds that section "
                                f"itself")
                else:
                    said.append(f"{key!r} - the app works that out")
            return _dump({
                "saved": False,
                "error": "the plan carries keys this tool does not store: "
                         + "; ".join(said)})
        payload = whole_numbers(payload)
        # **The third door checks what the other two do** (the critic on
        # row 2.6): a plan with no tyres decision was saved and certified
        # here, approved in the app, and spoke "Box this lap. RS.".
        from pitcrew.strategy.handover import stint_tyre_problems

        problems = stint_tyre_problems(payload)
        if problems:
            return _dump({"saved": False, "error": "plan refused",
                          "problems": problems})
        # **Stamped, like the other door.** `write_strategy` stamps and this
        # one did not, so a proposed plan approved in the app armed with no
        # `start_lap` - every stint then ends at `laps`, two stints share a
        # box lap, and `_box_now` fires every lap to the flag - no `context`,
        # so `arm` skips `planned.matches(actual)` and a plan for one circuit
        # arms at another, and no `expects`, so every per-lap comparison
        # reports nothing.
        from pitcrew.strategy.execution import stamp

        try:
            payload = stamp(store, event_id, payload)
        except ValueError as exc:
            return _dump({"saved": False, "error": str(exc)})

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
def shift_points(car_name: str, circuit_key: str = "") -> str:
    """The upshift tables issued for a car, newest first.

    With a `circuit_key`, only the table for that circuit - which is the one
    the beep will actually use, because a gearbox is cut for the circuit.
    """
    store = _store()
    try:
        if circuit_key:
            one = store.shift_points_for(car_name, circuit_key)
            return _dump(one.as_export() if one else None)
        return _dump([t.as_export() for t in store.list_shift_points(car_name)])
    finally:
        store.close()


@mcp.tool()
def write_shift_points(car_name: str, performance_rpm: dict,
                       circuit_key: str = "", fuel_saving_rpm: dict | None = None,
                       note: str = "") -> str:
    """Issue the upshift table for the gearbox in this car at this circuit. ⚠

    **This is what the driver hears at the wheel**, and it is the one piece of
    the setup that reaches him through the app rather than through GT7's own
    screens - so it is issued here with the setup it belongs to, never typed
    in by hand against last week's box.

    `performance_rpm` maps gear number to the rpm to upshift at when lap time
    is the objective. `fuel_saving_rpm` is the short-shift table for a
    fuel-bound stint - worth about 20% fuel for about 0.5 s/lap, and it lowers
    rear tyre wear with it. Both keyed by gear as `{"1": 8000, "2": 8100}`.

    Refused rather than stored where a fuel-saving point is at or above its
    own performance point: that is a swapped pair of columns, it is silent at
    the wheel, and it costs fuel in the direction the driver was told it saved.

    **A gear left out of `performance_rpm` does not beep.** That is the honest
    answer, not a gap to be filled: one car wants the limiter in every gear
    and another wants 8250 in all five, and any fallback sounds exactly like a
    measurement without being one.
    """
    store = _store()
    try:
        def table(raw) -> dict[int, float]:
            return {int(g): float(r) for g, r in (raw or {}).items()}

        issued = ShiftPoints(
            car_name=car_name, circuit_key=circuit_key or None,
            performance=table(performance_rpm),
            fuel_saving=table(fuel_saving_rpm),
            issued_by="race engineer (MCP)", issued_at=_today(), note=note)
        before = store.shift_points_for(car_name, circuit_key or None)
        table_id = store.save_shift_points(issued)
        store.note_engineer_write(
            "shift_points", target_id=table_id,
            author="race engineer (MCP)",
            summary=f"issued shift points for {car_name}"
                    + (f" at {circuit_key}" if circuit_key else ""),
            before=before.as_export() if before else None,
            after=issued.as_export())
        return _dump({
            "written": True, "shiftPointsId": table_id,
            "table": issued.as_export(),
            "note": "the beep uses this from the next session in this car at "
                    "this circuit. Gears absent from performanceRpm stay "
                    "silent.",
        })
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
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

    **A plan carries a playbook or it is refused.** This door used to store
    the payload as written - no `Handover.validate()`, so a plan with no
    playbook armed George on his defaults and a plan with a mistyped or
    forbidden action would have armed too. Deep Forest (strategy 27) and
    Daytona (17) both ran that way. The playbook is the `playbook` list beside
    the plan, as `references/race-planner.md` shows under "The write call";
    an EMPTY list is accepted and means "no adaptations", because a race can
    honestly be run to a plan with none - what is refused is the list being
    absent, which is the driver assuming a playbook exists. Every entry is
    validated (trigger, action, `when`) before anything is stored.
    """
    store = _store()
    try:
        payload = json.loads(plan) if isinstance(plan, str) else plan
    except json.JSONDecodeError as exc:
        return _dump({"written": False, "error": f"plan is not JSON: {exc}"})
    try:
        from pitcrew.strategy.certify import certify_for_event
        from pitcrew.strategy.execution import stamp
        from pitcrew.strategy.handover import from_dict

        section = (payload.get("handover")
                   if isinstance(payload.get("handover"), dict) else payload)
        if not isinstance(section, dict) or "playbook" not in section:
            store.note_engineer_write(
                "strategy", target_id=None, event_id=event_id,
                author="race engineer (MCP)",
                summary="refused: no playbook", after={"label": label})
            return _dump({
                "written": False,
                "error": ("no playbook: a plan needs a `playbook` list beside "
                          "it (empty means 'no adaptations'). The recipe is "
                          ".claude/skills/ludo/references/race-planner.md, "
                          "'The write call'."),
            })
        handover = from_dict(payload)
        problems = handover.validate()
        if problems:
            # A refusal leaves a trace: a plan that could not be loaded is
            # as much a fact about the weekend as one that was.
            store.note_engineer_write(
                "strategy", target_id=None, event_id=event_id,
                author="race engineer (MCP)",
                summary="refused: " + "; ".join(problems)[:200],
                after={"label": label, "problems": problems})
            return _dump({"written": False, "error": "plan refused",
                          "problems": problems})

        stamped = stamp(store, event_id, handover.plan)
        certificate = certify_for_event(store, event_id, stamped)
        # **The context check both approving doors make** (critic 2 on the
        # storage row). This one approved on `certified` alone, so last
        # round's file written against this event was approved, the good
        # plan demoted to a candidate, and the grid refused it with nothing
        # left to fall back on.
        from pitcrew.strategy.execution import built_for_another_race

        foreign = built_for_another_race(stamped, store.get_event(event_id))
        # **The certificate's refusals, and the mismatch under its own key**
        # (critic 2, pass 3): `certified: True`, "Driveable" and a refusal in
        # one reply is rule 13 inside a single document. It IS driveable; it
        # is for another race.
        refusals = list(certificate.refusals)
        approve = certificate.certified and foreign is None
        payload = handover.as_stored(stamped)
        payload["handover"]["certificate"] = {
            "warnings": list(certificate.warnings),
            "unchecked": list(certificate.unchecked),
        }
        strategy_id = store.save_strategy(
            event_id, payload, label=label or "written by the race engineer",
            evidence={"certified": certificate.certified,
                      "refusals": refusals,
                      "warnings": certificate.warnings,
                      "unchecked": certificate.unchecked,
                      "builtForAnotherRace": foreign},
            status="candidate")
        if approve:
            store.approve_strategy(strategy_id)
        if approve:
            summary = "approved"
        elif foreign:
            summary = "stored as a candidate - built for another race"
        else:
            summary = "stored as a candidate - it did not certify"
        store.note_engineer_write(
            "strategy", target_id=strategy_id, event_id=event_id,
            author="race engineer (MCP)", summary=summary,
            after={"label": label, "certified": certificate.certified,
                   "approved": approve})
        if approve:
            note = "approved and ready to arm."
        elif not certificate.certified:
            note = ("NOT approved: it did not certify, so the car cannot "
                    "execute it as written. Fix the refusals and write again.")
        else:
            note = (f"NOT approved: the {foreign}. The approved plan for this "
                    "event is unchanged. Write it against the right event, "
                    "or fix its context.")
        return _dump({
            "written": True, "strategyId": strategy_id,
            "approved": approve,
            "certified": certificate.certified,
            "refusals": refusals,
            "warnings": certificate.warnings,
            "unchecked": certificate.unchecked,
            "builtForAnotherRace": foreign,
            "unhandled": handover.unhandled(),
            "verdict": certificate.describe(),
            "note": note,
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
def measurements(car_name: str = "", circuit_key: str = "", metric: str = "",
                 zone: str = "", limit: int = 40) -> str:
    """Derived numbers already on file, newest first - so they are not
    re-derived off the frames every session.

    Every row carries its sample count, its noise floor and how that floor was
    obtained. **A null floor means it was never established, not zero**: a
    difference cannot be called resolvable against a floor nobody took.
    """
    store = _store()
    try:
        rows = store.measurements(
            car_name=car_name or None, circuit_key=circuit_key or None,
            metric=metric or None, zone=zone or None,
            limit=min(limit, MAX_ROWS))
        return _dump([row.as_export() for row in rows])
    finally:
        store.close()


@mcp.tool()
def axis_status(car_name: str, circuit_key: str = "", axis: str = "") -> str:
    """What is known about a slider axis on this car - **`untested` included**.

    With no `axis`, the whole board: which axes have never been tested here,
    which were tried on an instrument that could not resolve them, and which
    are settled. On 8 Sep 2026 ride height had never been A/B'd on any car in
    the programme and there was no way to find that out; this is that call.

    With an `axis`, its current verdict and the history behind it. An axis
    nobody has touched answers `untested` rather than answering nothing.
    """
    store = _store()
    try:
        if not axis:
            return _dump(store.untested_axes(car_name, circuit_key or None))
        current = store.verdict_for(car_name, axis, circuit_key or None)
        history = store.verdicts(car_name=car_name, axis=axis)
        return _dump({"current": current.as_export(),
                      "history": [v.as_export() for v in history]})
    finally:
        store.close()


# ------------------------------------------------- authoritative writes 2
#
# These two land rows the engineer will reason from next week. They apply,
# like the writes above them, and for the same reason: a number that lives
# only in a conversation is re-derived from scratch every session and cannot
# be compared with itself.

@mcp.tool()
def write_measurement(car_name: str, metric: str, value: float, unit: str,
                      scope: str, source: str, circuit_key: str = "",
                      zone: str = "", config_ref: str = "",
                      config_label: str = "", n: int = 0, n_basis: str = "",
                      noise_floor: float | None = None,
                      floor_method: str = "", tool: str = "",
                      session_ids: list | None = None,
                      game_version: str = "", measured_on: str = "",
                      note: str = "") -> str:
    """Record one derived number, with what is needed to trust or refuse it. ⚠

    `scope` is `corner` | `lap` | `stint` | `session` | `car`, and a
    corner-scoped row has to name its `zone`. `source` is `MEASURED`,
    `DERIVED`, `DOCTRINE`, `ASSUMED` or `DRIVER REPORT` - rule 5, nothing
    derived is presented as measured.

    **`noise_floor` left out means the floor was never established.** It is
    not zero, and a literal 0.0 is refused: a floor of zero says every
    difference is resolvable, which is how a change of 0.0006 got read as a
    change. Where a floor is given, `floor_method` has to say how it was
    obtained.

    **`n` of 0 means the sample count was not recorded**, and it is stored as
    null rather than as a count of none. Where n is given, `n_basis` says what
    it counts - "n=15" of clean laps and of braking events are not the same
    claim (rule 4).

    ⛔ `config_ref` is a POINTER to the configuration - `huracan-daytona#s145`,
    a revision label, a hash. Never the slider values: `brain/car-state/
    <car>-<circuit>.md` is the only place one may be written, and a copy here
    is the second copy that was removed on 5 Sep. A ref that reads like an
    assignment is refused by name.
    """
    from pitcrew.engineer.measurements import Measurement

    store = _store()
    try:
        row = Measurement(
            car_name=car_name, metric=metric, value=float(value), unit=unit,
            scope=scope, source=source, circuit_key=circuit_key or None,
            zone=zone or None, config_ref=config_ref or None,
            config_label=config_label or None,
            n=int(n) if n else None, n_basis=n_basis or None,
            noise_floor=None if noise_floor is None else float(noise_floor),
            floor_method=floor_method or None, tool=tool or None,
            session_ids=tuple(int(i) for i in (session_ids or ())),
            game_version=game_version or None,
            measured_on=measured_on or _today(), note=note or None)
        row_id = store.record_measurement(row)
        store.note_engineer_write(
            "measurement", target_id=row_id, author="race engineer (MCP)",
            summary=f"{metric} = {value} {unit} for {car_name}"
                    + (f" at {circuit_key}" if circuit_key else ""),
            after=row.as_export())
        return _dump({"written": True, "measurementId": row_id,
                      "measurement": row.as_export()})
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def write_verdict(car_name: str, axis: str, verdict: str, why: str,
                  circuit_key: str = "", direction: str = "",
                  instrument: str = "", instrument_floor: float | None = None,
                  measurement_ids: list | None = None,
                  decided_on: str = "", game_version: str = "") -> str:
    """Record what an axis is believed to do, and what said so. ⚠

    `verdict` is `confirmed` | `refuted` | `untested` | `unresolvable`.

    **`unresolvable` is not `refuted`.** The first says the instrument could
    not see the change; the second says the car did not respond to it. On
    1 Sep `lsd_a` was recorded as refuted on the strength of a rear wheel-speed
    split that then sat at a median of 0.0000 through a six-click change of
    that very axis, while a rotation index moved to twice its own floor. That
    was `unresolvable` all along, and calling it `refuted` closed an axis that
    was open.

    So: `confirmed` and `refuted` have to name the **direction** tested and the
    **instrument** used - a verdict on an axis from a test of half of it is the
    other half of the same defect - and `unresolvable` has to name the
    instrument and the floor it could not clear.

    Append-only. A wrong verdict is retired by writing a better one; the old
    row stays, because why the instrument was blind outlives the call.
    """
    from pitcrew.engineer.measurements import Verdict

    store = _store()
    try:
        row = Verdict(
            car_name=car_name, axis=axis, verdict=verdict, why=why,
            circuit_key=circuit_key or None, direction=direction or None,
            instrument=instrument or None,
            instrument_floor=(None if instrument_floor is None
                              else float(instrument_floor)),
            measurement_ids=tuple(int(i) for i in (measurement_ids or ())),
            decided_on=decided_on or _today(),
            game_version=game_version or None)
        row_id = store.record_verdict(row)
        store.note_engineer_write(
            "verdict", target_id=row_id, author="race engineer (MCP)",
            summary=f"{axis} {verdict} on {car_name}"
                    + (f" at {circuit_key}" if circuit_key else ""),
            after=row.as_export())
        return _dump({"written": True, "verdictId": row_id,
                      "verdict": row.as_export()})
    except Exception as exc:                                 # noqa: BLE001
        return _dump({"written": False, "error": f"{type(exc).__name__}: {exc}"})
    finally:
        store.close()


@mcp.tool()
def write_qualifying_plan(event_id: int, plan: str, label: str = "") -> str:
    """Write the qualifying plan: fuel, runs and what each one is for.

    **The same door the race plan comes through**, and deliberately not a
    second one. `race/qualifying_plan.build` still exists and still costs a
    plan from this car's measured burn - but under the 29 Aug architecture
    that is the app authoring, and it stays only as the fallback for an event
    nobody has written one for.

    `plan` is JSON: `{"fuel_l": 22.0, "runs": [{"laps": 3, "flying_laps": 1}],
    "assumptions": [...], "notes": "..."}`. Everything in it is declared - the
    litres are the engineer's call, not a measurement this app took.

    Not certified. `certify.py` prices stints, fuel and stops against a race
    distance, and a qualifying run has none of those; pretending it applied
    would be a check that passes because it tested nothing.
    """
    store = _store()
    try:
        payload = json.loads(plan) if isinstance(plan, str) else plan
    except json.JSONDecodeError as exc:
        return _dump({"written": False, "error": f"plan is not JSON: {exc}"})
    try:
        if not isinstance(payload, dict) or payload.get("fuel_l") is None:
            return _dump({
                "written": False,
                "error": "a qualifying plan has to say how much fuel goes in "
                         "- that is the whole point of one. Qualifying is the "
                         "run where every litre is mass dragged round the "
                         "only lap that counts."})
        plan_id = store.save_qualifying_plan(event_id, payload, label=label)
        store.note_engineer_write(
            "quali_plan", target_id=plan_id, event_id=event_id,
            author="race engineer (MCP)",
            summary=f"qualifying plan, fuel to {payload['fuel_l']} litres",
            after=payload)
        return _dump({"written": True, "planId": plan_id,
                      "note": "the Strategy screen shows this instead of the "
                              "app's own costing."})
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
