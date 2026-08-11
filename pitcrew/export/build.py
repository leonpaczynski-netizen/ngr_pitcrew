"""One call that turns a recorded session into a validated export payload.

Everything upstream of here is deliberately small and testable in isolation.
This is the join: read the session out of the store, aggregate it, and hand
back a payload that has already been validated — or refuse.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace

from pitcrew.analysis import thresholds
from pitcrew.analysis.corners import (
    CountedLap,
    aggregate_corners,
    bottoming_reference,
)
from pitcrew.analysis.gearing import gearing_export
from pitcrew.analysis.resolve import resolve_corner_model
from pitcrew.analysis.session import (
    LapInput,
    counted_laps,
    exclusion_note,
    lap_export,
    session_export,
)
from pitcrew.analysis.wear import wear_export
from pitcrew.race.outcome import fuel_left_note, race_outcome
from pitcrew.export.payload import Derived, Meta, build_payload
from pitcrew.store.tyres import get_by_code

# GT7 multipliers are shown as "Off" or "Nx". "Off" means the thing does not
# happen at all, which is a factor of zero, not of one.
MULTIPLIER_OFF = "Off"


def multiplier_factor(setting: str | None) -> float | None:
    """Parse "4x" to 4.0 and "Off" to 0.0. None when it was never set."""
    if not setting:
        return None
    text = setting.strip()
    if text.lower() == "off":
        return 0.0
    if text.lower().endswith("x"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def session_lap_inputs(store, session_id: int) -> list[LapInput]:
    return _rows_to_laps(store, store.list_laps(session_id))


def event_lap_inputs(store, event_id: int, kind: str) -> list[LapInput]:
    """Every lap of every run of this kind, numbered continuously.

    Practice accumulates: a driver who goes out three times has one body of
    evidence, not three. The stored lap numbers restart at 1 each run, so they
    are renumbered here - two laps both called "lap 1" in one export would be
    unreadable.
    """
    rows = store.list_event_laps(event_id, kind)
    laps = _rows_to_laps(store, rows)
    return [replace(lap, lap_num=index) for index, lap in enumerate(laps, 1)]


def _rows_to_laps(store, rows) -> list[LapInput]:
    out = []
    for row in rows:
        frames = None
        stored = store.get_lap_frames(row["id"])
        if stored:
            frames = stored["frames"]
        out.append(LapInput(
            lap_num=row["lap_num"],
            lap_time_ms=row["lap_time_ms"],
            fuel_start=row["fuel_start"],
            fuel_end=row["fuel_end"],
            compound=row["compound"],
            fuel_map=row["fuel_map"],
            is_pit_lap=bool(row["is_pit_lap"]),
            is_out_lap=bool(row["is_out_lap"]),
            excluded=bool(row["excluded"]),
            exclusion_reason=row["exclusion_reason"],
            wear_front=row["wear_front"],
            wear_rear=row["wear_rear"],
            gear_ratios=_ratios(row),
            frames=frames,
        ))
    return out


def _ratios(row) -> list[float] | None:
    raw = row["gear_ratios"] if "gear_ratios" in row.keys() else None
    return json.loads(raw) if raw else None


def _dominant_compound(laps: list[LapInput]) -> str | None:
    """The compound most of the counted laps ran on.

    None rather than a guess when nothing was tagged — the tune builder reads
    an absent compound as "not recorded", which is true.
    """
    tags = [lap.compound for lap in counted_laps(laps) if lap.compound]
    if not tags:
        return None
    return Counter(tags).most_common(1)[0][0]


def _reference_frames(laps: list[LapInput]) -> list[dict] | None:
    """The fastest counted lap that has frames — the corner model's reference."""
    candidates = [lap for lap in counted_laps(laps) if lap.frames]
    if not candidates:
        return None
    return min(candidates, key=lambda lap: lap.lap_time_ms).frames


def build_session_export(store, session_id: int, *, notes: str = "",
                         calibrated_at_race_multiplier: bool = True) -> dict:
    """The payload for one run on its own."""
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"no session with id {session_id}")
    return _build(store, session, session_lap_inputs(store, session_id),
                  notes=notes,
                  calibrated_at_race_multiplier=calibrated_at_race_multiplier)


def build_event_export(store, event_id: int, *, kind: str = "practice",
                       notes: str = "",
                       calibrated_at_race_multiplier: bool = True) -> dict:
    """The payload for everything run at this event.

    This is what the driver exports: three runs at one circuit are one body of
    evidence about one car, and splitting them would hand the tune builder
    three thin samples instead of one usable one.
    """
    sessions = store.list_sessions(event_id, kind)
    if not sessions:
        raise ValueError("nothing recorded for this event yet")
    laps = event_lap_inputs(store, event_id, kind)
    return _build(store, _merged_session(sessions), laps, notes=notes,
                  calibrated_at_race_multiplier=calibrated_at_race_multiplier)


def _merged_session(sessions: list[dict]) -> dict:
    """One session record standing for the run of runs.

    Dated from the first run and described by the first run that actually saw
    each stream fact - a later run started before GT7 was streaming would
    otherwise erase what an earlier one measured.
    """
    ordered = sorted(sessions, key=lambda s: s["started_at"])
    merged = dict(ordered[0])
    for key in ("packet_format", "car_category", "fuel_capacity_l",
                "setup_sheet_id"):
        merged[key] = next(
            (s[key] for s in ordered if s[key] is not None), None)
    return merged


def _build(store, session: dict, laps: list[LapInput], *, notes: str,
           calibrated_at_race_multiplier: bool) -> dict:
    """Assemble the `gt7-pitcrew/1.2` payload."""
    event = store.get_event(session["event_id"])
    if event is None:
        raise ValueError("session has no event")

    counted = counted_laps(laps)

    compound = _compound_full_name(_dominant_compound(laps))
    meta = Meta(
        car=event["car_name"] or "unknown",
        circuit=_circuit_name(event),
        date=(session["started_at"] or "")[:10],
        session_type=session["kind"],
        packet=session["packet_format"] or "A",
        car_category=session["car_category"],
        game_version=event["game_version"],
        compound_front=compound,
        compound_rear=compound,
        abs_setting=event["abs_setting"],
        tcs=event["tcs"],
        countersteer=(None if event["countersteer"] is None
                      else bool(event["countersteer"])),
        tyre_wear_mult=event["tyre_wear_mult"],
        fuel_mult=event["fuel_mult"],
    )

    corners = None
    reference = _reference_frames(laps)
    model = resolve_corner_model(store, event["track"], event["layout"], reference)
    counted_with_frames = [CountedLap(lap.lap_num, lap.frames)
                           for lap in counted if lap.frames]
    bottoming_ref = None
    if model is not None and counted_with_frames:
        meta.corner_model = model.as_meta()
        bottoming_ref = bottoming_reference(counted_with_frames)
        corners = aggregate_corners(model, counted_with_frames, bottoming_ref)

    setup = None
    driver_changes = None
    sheet_gears = None
    if session["setup_sheet_id"]:
        sheet = store.get_setup_sheet(session["setup_sheet_id"])
        if sheet is not None:
            setup = sheet.as_export()
            sheet_gears = sheet.gears
            changes = store.list_setup_changes(session["id"])
            driver_changes = [c.as_export() for c in changes] or None

    gearing = gearing_export(counted, sheet_gears)
    strategy = _strategy_section(store, event["id"])

    range_record = None
    if event["car_name"]:
        record = store.get_range_record(event["car_name"])
        if record is not None:
            range_record = record.as_export()

    all_notes = " ".join(part for part in (exclusion_note(laps), notes) if part)

    return build_payload(
        meta,
        setup=setup,
        driver_changes=driver_changes,
        range_record=range_record,
        session=session_export(laps, fuel_capacity_l=session["fuel_capacity_l"]),
        laps=[lap_export(lap) for lap in laps],
        corners=corners,
        wear=wear_export(
            laps, calibrated_at_race_multiplier=calibrated_at_race_multiplier),
        gearing=gearing,
        strategy=strategy,
        derived=Derived(thresholds.as_export(), bottoming_ref_mm=bottoming_ref),
        notes=all_notes,
    )


def _strategy_section(store, event_id: int) -> dict | None:
    """The approved plan, its assumptions, and every call the engineer made.

    Omitted entirely when no plan is approved - a skeleton of nulls would read
    as "planned, measured nothing" rather than "not planned".
    """
    approved = store.get_approved_strategy(event_id)
    if approved is None:
        return None

    section = dict(approved["plan"].get("export") or {})
    if not section:
        return None

    assumptions = section.setdefault("assumptions", {})
    event = store.get_event(event_id)
    if event is not None:
        # Required: at 1 L/s against a 2.5 default this is the number that
        # decides the race, and a default standing in its place is unreadable.
        assumptions["refuelRateLps"] = event["refuel_rate_lps"]
        assumptions["mandatoryStops"] = event["mandatory_stops"]

    calls = _calls_made(store, event_id)
    if calls:
        section["callsMade"] = calls

    outcome = _outcome(store, event_id, section)
    if outcome:
        section["outcome"] = outcome
    return section


def _outcome(store, event_id: int, section: dict) -> str:
    """What happened, from the race laps. Omitted when no race was run."""
    race_laps = event_lap_inputs(store, event_id, "race")
    if not race_laps:
        return ""
    plan = section.get("plan") or {}
    declined = sum(1 for call in section.get("callsMade") or []
                   if call.get("accepted") is False)
    text = race_outcome(
        race_laps,
        planned_stops=plan.get("stops"),
        planned_pit_laps=[plan["pitLap"]] if plan.get("pitLap") else None,
        binding_constraint=section.get("bindingConstraint"),
        declined_calls=declined)
    fuel = fuel_left_note(race_laps)
    return f"{text} {fuel}".strip() if fuel else text


def _calls_made(store, event_id: int) -> list[dict]:
    """Every call, including the ones declined.

    A plan offered and refused is evidence about the model; dropping it makes
    the model look better than it was.
    """
    calls: list[dict] = []
    for run in store.list_race_runs(event_id):
        for revision in store.list_revisions(run["id"]):
            calls.append({
                "lap": revision["lap_num"],
                "call": revision["reason"],
                "accepted": revision["accepted"],
                "confidence": revision["plan"].get("confidence", "unstated"),
            })
    return calls


def _compound_full_name(code: str | None) -> str | None:
    """"RM" -> "Racing Medium". The contract wants the full GT7 name."""
    if not code:
        return None
    compound = get_by_code(code)
    return compound.name if compound else code


def _circuit_name(event: dict) -> str:
    track = event["track"] or "unknown"
    layout = event["layout"]
    return f"{track} ({layout})" if layout else track
