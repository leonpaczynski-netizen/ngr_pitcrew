"""One call that turns a recorded session into a validated export payload.

Everything upstream of here is deliberately small and testable in isolation.
This is the join: read the session out of the store, aggregate it, and hand
back a payload that has already been validated — or refuse.
"""
from __future__ import annotations

import json
from dataclasses import replace

from pitcrew.analysis import thresholds
from pitcrew.analysis.corners import (
    CountedLap,
    aggregate_corners,
    bottoming_reference,
    length_gate,
    observed_minimum,
)
from pitcrew.analysis import distance
from pitcrew.analysis.gearing import gearing_export
from pitcrew.analysis.resolve import resolve_corner_model
from pitcrew.race.expectations import audit_line_from_laps
from pitcrew.analysis.runs import classify_exclusions, runs_export, split_runs
from pitcrew.analysis.incidents import (
    as_export as incidents_export,
    find_incidents,
    stored_or_read,
    thresholds_export as incident_thresholds,
)
from pitcrew.analysis.session import (
    LapInput,
    counted_laps,
    diagnostic_laps,
    exclusion_note,
    lap_export,
    session_export,
)
from pitcrew.analysis.wear import wear_export
from pitcrew.race.outcome import fuel_left_note, race_outcome
from pitcrew.export.payload import (Derived, Meta,
                                    build_payload)
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


def evidence_lap_inputs(store, event_id: int, *,
                        hydrate: set[int] | None = None) -> list[LapInput]:
    """Practice plus any rehearsal race, renumbered continuously.

    Same renumbering as `event_lap_inputs` and for the same reason: two
    laps both called "lap 1" are unreadable, and worse, put two different
    runs at the same number where anything keyed on it cannot tell them
    apart.
    """
    laps = _rows_to_laps(store, store.list_evidence_laps(event_id),
                         hydrate=hydrate)
    return [replace(lap, lap_num=index) for index, lap in enumerate(laps, 1)]


def event_lap_inputs(store, event_id: int, kind: str = "practice", *,
                     hydrate: set[int] | None = None) -> list[LapInput]:
    """Every lap of every run of this kind, numbered continuously.

    Practice accumulates: a driver who goes out three times has one body of
    evidence, not three. The stored lap numbers restart at 1 each run, so they
    are renumbered here - two laps both called "lap 1" in one export would be
    unreadable, and worse, would put two different runs' laps at the same
    number where anything keyed on lap number could not tell them apart.

    `hydrate` limits which laps decode their telemetry, for callers that only
    need frames on a few. **It is the only thing a caller may vary.** The
    strategy path used to have a loader of its own, and it quietly dropped the
    session id and the continuous numbering - so every lap of every evening
    looked like one session, and a compound comparison that depends on
    "the same session" could not tell that no two compounds ever shared one.
    """
    rows = store.list_event_laps(event_id, kind)
    laps = _rows_to_laps(store, rows, hydrate=hydrate)
    return [replace(lap, lap_num=index) for index, lap in enumerate(laps, 1)]


def mark_incidents(laps: list[LapInput]) -> tuple[list[LapInput], dict]:
    """Find the laps with an off or a spin in them and mark them.

    **Not in place**, despite what this said for a long time: the marked laps
    come back as new objects from `replace`, and the caller's list is
    untouched. That is what lets `prompts/context` hand its raw laps to
    `build_event_export` and classify its own copy separately.

    Only laps whose frames were decoded can be judged. A lap without them is
    left alone rather than assumed clean — not measured is not the same as
    nothing happened, and the export says which by carrying the sample count.
    """
    incidents = find_incidents(laps, stored_or_read)
    marked = [replace(lap, incident=True,
                      incident_note=incidents[lap.lap_num].describe())
              if lap.lap_num in incidents else lap
              for lap in laps]
    return marked, incidents


def _rows_to_laps(store, rows, *, hydrate: set[int] | None = None) -> list[LapInput]:
    out = []
    for row in rows:
        frames = None
        if hydrate is None or row["id"] in hydrate:
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
            wear_fl=row["wear_fl"],
            wear_fr=row["wear_fr"],
            wear_rl=row["wear_rl"],
            wear_rr=row["wear_rr"],
            gear_ratios=_ratios(row),
            frames=frames,
            session_id=row["session_id"],
            game_version=_column(row, "game_version"),
            tyres_fresh=_tyres_fresh(row),
            tyres_changed=_tri_state(row, "tyres_changed"),
            tod_start_ms=_column(row, "tod_start_ms"),
            tod_end_ms=_column(row, "tod_end_ms"),
            standing_start_ms=_column(row, "standing_start_ms"),
            practice_mode=_column(row, "practice_mode"),
            setup_sheet_id=_column(row, "setup_sheet_id"),
            rehearsal=bool(_column(row, "rehearsal")),
            crawl_s=_column(row, "crawl_s"),
            off_track_s=_column(row, "off_track_s"),
            spin_s=_column(row, "spin_s"),
        ))
    return out


def _tyres_fresh(row) -> bool | None:
    """The driver's declaration, kept tri-state all the way to the export.

    `None` is not `False`: he has not said, which is different from saying the
    set carried over.
    """
    return _tri_state(row, "tyres_fresh")


def _column(row, column: str):
    """A column that may predate the row it is being read from."""
    return row[column] if column in row.keys() else None


def _tri_state(row, column: str) -> bool | None:
    """A stored flag that has three states, one of which is "not asked".

    Absent from the row as well as null in it: a lap recorded before the
    column existed has not answered the question either.
    """
    value = row[column] if column in row.keys() else None
    return None if value is None else bool(value)


def _ratios(row) -> list[float] | None:
    raw = row["gear_ratios"] if "gear_ratios" in row.keys() else None
    return json.loads(raw) if raw else None


def _compounds_run(runs) -> list[str]:
    """Every compound the session actually ran, in the order it ran them.

    **Never a vote.** The 11 Aug Monza export ran three compounds across five
    runs and declared one, because `meta.compound` was the most common tag and
    two thirds of the session lost its argument silently. A reader given a
    single compound reads a single-compound session; the compound that wins a
    vote is not the compound that was on the car.

    An untagged run contributes nothing rather than a guess.
    """
    seen: list[str] = []
    for run in runs:
        code = run.compound
        if code and code not in seen:
            seen.append(code)
    return seen


def _counted_lap(lap: LapInput) -> CountedLap:
    """A lap in the shape the corner aggregates read.

    **The sheet id travels with it.** Ride height and spring rate are setup
    values, so the height a wheel bottoms at is a property of the sheet rather
    than of the event, and the bottoming reference is keyed on it.
    """
    return CountedLap(lap.lap_num, lap.frames,
                      setup_sheet_id=lap.setup_sheet_id)


def _anchor_note(anchor) -> str:
    """What the circuit anchor did, in the notes, or why it did nothing.

    **Never silent.** A corrected distance that does not say it was corrected
    is a derived number wearing a measured one's clothes (CLAUDE.md rule 5),
    and an export from a circuit whose length is unknown would otherwise be
    indistinguishable from one that was anchored.
    """
    if not anchor.ran:
        return ("Lap distance is integrated from speed and was NOT anchored: "
                "this layout has no length in the catalogue, so every corner "
                "window carries the integration bias uncorrected - measured "
                "at 0.2-0.9% short on the three circuits that can be checked.")
    said = (f"Lap distance anchored to the circuit's own "
            f"{anchor.circuit_length_m:.0f} m: `lap_distance_m` is integrated "
            f"from speed, not broadcast, and runs short.")
    if anchor.refused:
        worst = max(length for _, length in anchor.refused)
        said += (f" {len(anchor.refused)} lap(s) could not be anchored and "
                 f"carry a null distance rather than a corrected one - the "
                 f"furthest integrated {worst:.0f} m, which is a swallowed "
                 f"crossing or a fragment rather than an imprecise lap.")
    if anchor.teleported:
        biggest = max(found.longest_m for _, found in anchor.teleported)
        said += (f" A further {len(anchor.teleported)} lap(s) carry a null "
                 f"distance because the car JUMPED position mid-lap, the "
                 f"furthest by {biggest:.0f} m in a single frame - a reset or "
                 f"a garage return. Their integrated length is plausible, so "
                 f"no length check can see them; it is read off the position "
                 f"channel.")
    return said


def _reference_frames(laps: list[LapInput]) -> list[dict] | None:
    """The fastest counted lap that has frames — the corner model's reference."""
    candidates = [lap for lap in counted_laps(laps) if lap.frames]
    if not candidates:
        return None
    return min(candidates, key=lambda lap: lap.lap_time_ms).frames


def build_session_export(store, session_id: int, *, notes: str = "",
                         game_version: str | None = None,
                         calibrated_at_race_multiplier: bool = True) -> dict:
    """The payload for one run on its own."""
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"no session with id {session_id}")
    return _build(store, session, session_lap_inputs(store, session_id),
                  notes=notes, game_version=game_version,
                  calibrated_at_race_multiplier=calibrated_at_race_multiplier)


def build_event_export(store, event_id: int, *, kind: str = "practice",
                       notes: str = "",
                       game_version: str | None = None,
                       calibrated_at_race_multiplier: bool = True,
                       laps: list[LapInput] | None = None) -> dict:
    """The payload for everything run at this event.

    This is what the driver exports: three runs at one circuit are one body of
    evidence about one car, and splitting them would hand the tune builder
    three thin samples instead of one usable one.

    `laps` lets a caller that has already paid for the decode hand it over.
    **The prompt builder had, and was paying twice**: `prompts/context` reads
    every lap of the event to build its prose, then calls this, which read the
    identical laps again - 3.2 s of duplicated decoding on one event.

    They must be the RAW laps, exactly as `event_lap_inputs` returns them,
    because this classifies them itself. That is safe to share: neither
    `mark_incidents` nor `classify_exclusions` mutates - both build new lists
    with `replace` - so a caller's own classification cannot reach this one.
    """
    sessions = store.list_sessions(event_id, kind)
    if not sessions:
        raise ValueError("nothing recorded for this event yet")
    if laps is None:
        laps = event_lap_inputs(store, event_id, kind)
    return _build(store, _merged_session(sessions), laps, notes=notes,
                  game_version=game_version,
                  calibrated_at_race_multiplier=calibrated_at_race_multiplier)


def drivetrain_of(store, event) -> tuple[str | None, str | None]:
    """Which wheels are driven, and on whose authority.

    GT7 broadcasts no drivetrain channel and the torque vectors that might have
    inferred one read zero on this stream, so it is told or it is unknown.
    Asking per event meant it was usually unknown: two of three events on file
    have never been told, and `wheelspin` was watching all four wheels on both.

    **The catalogue closes that without inventing anything.** `cars.drivetrain`
    is seeded from GT7's own car list, so the model of car is known even when
    nobody has said. It is a weaker claim than a declaration - it describes the
    car as shipped and cannot know about an engine swap, which this league's
    open tuning permits - so it is returned with its source and the export says
    which it had. A declaration on the event always wins.
    """
    declared = (event or {}).get("drivetrain")
    if declared:
        return declared, "declared"
    name = (event or {}).get("car_name")
    if not name:
        return None, None
    car = store.car_by_name(name)
    value = (car or {}).get("drivetrain")
    return (value, "catalogue") if value else (None, None)


def _session_field(session, name):
    """A session column that may predate the row it is read from."""
    if hasattr(session, "keys"):
        return session[name] if name in session.keys() else None
    return session.get(name)


def _merged_session(sessions: list[dict]) -> dict:
    """One session record standing for the run of runs.

    Dated from the first run and described by the first run that actually saw
    each stream fact - a later run started before GT7 was streaming would
    otherwise erase what an earlier one measured.
    """
    ordered = sorted(sessions, key=lambda s: (s["started_at"], s["id"]))
    merged = dict(ordered[0])
    # **Every session's id, not just the one standing for them all.**
    # `setup_changes` is per session, and reading only the merged id lost
    # every change made in a later run of the same event: Red Bull Ring ran
    # `de_r` 32 in session 93 and 38 in 94, and the payload came out naming
    # the v1 sheet, a gearbox that sheet does not hold, and no statement that
    # anything had moved. The reader would have diagnosed a car on de_r 32.
    merged["session_ids"] = [s["id"] for s in ordered]

    # **An event may not span two versions of the game.** Everything else here
    # merges by picking the first run that had an answer, and for a packet
    # format or a fuel capacity that is right. For the GT7 version it would be
    # a lie: this export says "three runs at one circuit are one body of
    # evidence about one car", and laps taken either side of a physics update
    # are not one body of evidence about anything.
    #
    # 1.71 (20 Aug 2026) reworked the tyre model, per-car steering geometry,
    # damper attenuation and the adjustment ranges of suspension, differential
    # and aero. Event 1 holds 44 sessions from 11 to 21 August. Flattening
    # those into one payload under a single `meta.gameVersion` would hand the
    # tune builder pre- and post-patch wear in one array with nothing marking
    # the join - and CLAUDE.md §7 would rather refuse than emit that.
    seen = sorted({v for v in (_session_field(s, "game_version") for s in ordered)
                   if v})
    if len(seen) > 1:
        # **Summarised, not enumerated.** The first version of this refusal
        # listed every session on both sides, which on event 1 was 38 ids in
        # one sentence - a refusal nobody reads is barely better than none.
        # Each side gets a count and a date range, and the ids are named only
        # for the smaller side, because that is the one he will split off or
        # exclude.
        sides = {v: [s for s in ordered
                     if _session_field(s, "game_version") == v] for v in seen}
        smallest = min(sides, key=lambda v: len(sides[v]))
        parts = []
        for v, runs in sides.items():
            span = f"{str(runs[0]['started_at'])[:10]}"
            if str(runs[-1]["started_at"])[:10] != span:
                span += f" to {str(runs[-1]['started_at'])[:10]}"
            part = f"{v}: {len(runs)} session{'s' if len(runs) != 1 else ''}, {span}"
            if v == smallest and len(runs) <= 6:
                part += " (" + ", ".join(str(s["id"]) for s in runs) + ")"
            parts.append(part)
        raise ValueError(
            f"this event spans {len(seen)} GT7 versions and cannot be exported "
            f"as one body of evidence - " + "; ".join(parts) +
            ". Export the sides separately, or exclude the sessions recorded "
            "under the other version.")
    merged["game_version"] = seen[0] if seen else None

    for key in ("packet_format",
                "setup_sheet_id", "practice_intent", "practice_mode"):
        merged[key] = next(
            (s[key] for s in ordered if s[key] is not None), None)

    # **The class comes from a run whose car identity holds.** This took the
    # first non-null in start order, and on event 2 that was session 11 - a
    # `GR3` reading on an event whose car is a road car - so the payload
    # declared `meta.carCategory: Gr.3` for the whole event. A session the
    # store has flagged is not a witness to what the car was; a session that
    # never answered (`identity_status` null, a row older than the column) is
    # not accused and still counts.
    trusted = [s for s in ordered
               if (_session_field(s, "identity_status") or "ok") == "ok"]
    merged["car_category"] = next(
        (s["car_category"] for s in trusted if s["car_category"] is not None),
        None)
    # Fuel capacity is merged on plausibility, not on presence. GT7 reports a
    # 0 L tank for an electric car *and* for a packet that arrived before the
    # car had loaded, and event 3's first session opened on the second: its
    # 0.0 beat the 100.0 four later sessions measured, asserting an electric
    # car whose own laps burned 7.28 L each. A tank that was seen filling is
    # the stronger evidence whichever run saw it.
    merged["fuel_capacity_l"] = next(
        (s["fuel_capacity_l"] for s in ordered
         if s["fuel_capacity_l"] is not None and s["fuel_capacity_l"] > 0),
        next((s["fuel_capacity_l"] for s in ordered
              if s["fuel_capacity_l"] is not None), None))
    return merged


# GT7's own token against the contract's vocabulary. The stream reports the
# N-class as a group rather than as a number, so `GRN` cannot become `N500`
# here - the PP that would decide it is not in the packet.
CAR_CATEGORIES = {
    "GR1": "Gr.1", "GR2": "Gr.2", "GR3": "Gr.3", "GR4": "Gr.4",
    "GRB": "Gr.B", "GRX": "Gr.X", "GRN": "Gr.N",
}


def _car_category(token: str | None) -> str | None:
    """`GR3` -> `Gr.3`. Converted here, at the boundary, and nowhere else.

    The raw token is what the stream says and is what the store keeps; the
    contract's §2 vocabulary is what the consumer reads. A token it does not
    know reads as a car class that does not exist, so an unmapped one is
    passed through unchanged and refused by the validator rather than
    silently renamed into something plausible.
    """
    if not token:
        return None
    return CAR_CATEGORIES.get(token.strip().upper(), token)


def _fuel_capacity(session) -> tuple[float | None, str]:
    """The tank, and what to say about it when it could not be read.

    A stored 0 is not an electric declaration. It is what the packet carries
    before the car has loaded as well as what it carries for a car with no
    tank, and the two are indistinguishable in the feed. Exporting the zero
    switches the 1.4 lap-validity gate off for the whole event
    (`fuel_implausible_laps` skips a capacity of 0) and removes the fuel
    constraint from every race plan, with nothing in the payload saying so -
    so it goes out as not measured, and says which.
    """
    capacity = _session_field(session, "fuel_capacity_l")
    if capacity is None or capacity > 0:
        return capacity, ""
    return None, (
        "Fuel capacity read 0 L on every run of this event. GT7 reports 0 both "
        "for a car with no tank and for a packet that arrived before the car "
        "loaded, so this is exported as not measured rather than as an "
        "electric car - a zero would have switched the fuel plausibility "
        "check off for every lap here.")


def _build(store, session: dict, laps: list[LapInput], *, notes: str,
           game_version: str | None = None,
           calibrated_at_race_multiplier: bool) -> dict:
    """Assemble the `gt7-pitcrew/1.9` payload."""
    event = store.get_event(session["event_id"])
    if event is None:
        raise ValueError("session has no event")

    # Resolved once, and used by both the corner aggregation and the
    # thresholds block, so a payload can never say one thing in `wheelspin`
    # and another in `derived`.
    drivetrain, drivetrain_source = drivetrain_of(store, event)

    # Applied before anything is aggregated, so `lapsCounted`, `bestLapMs`,
    # the wear rates and the gearing all see one set of counted laps rather
    # than each deciding for itself which laps were real.
    # **Incidents first, then the classification.** The classifier has to
    # know which laps had something happen in order to name the reason, and
    # nothing may take a median before the 28-second spin has left the set it
    # would be taken from. Marking is a separate pass rather than a second
    # classify: running the classifier twice rewrites `exclusionReason` in
    # place and the driver's own words - "spun at T4" - do not survive it.
    laps, incidents = mark_incidents(laps)
    fuel_capacity_l, capacity_note = _fuel_capacity(session)
    laps = classify_exclusions(laps, fuel_capacity_l)

    # **Anchored to the circuit here, before anything is derived from it.**
    #
    # `lap_distance_m` is not in the packet - `telemetry/recorder.py`
    # integrates it from speed - and measured against each circuit's own
    # length it comes out 0.2-0.9% SHORT on all three circuits with laps on
    # file, while individual laps range from a third of a lap to twice one.
    # The bias shifts every corner window in every export, and corner
    # aggregates are what Ludo reads to build a setup.
    #
    # Anchor what can be anchored, null what cannot. **Once, on `laps`**, so
    # `counted`, `diagnostic` and `runs` all inherit one answer rather than
    # each being corrected separately - which was the first version of this
    # and is how two sets of the same laps come to disagree about where a
    # corner is. See `analysis/distance.py`.
    anchor = distance.anchor(laps, distance.circuit_length(store, event))
    laps = anchor.laps

    counted = counted_laps(laps)
    diagnostic = diagnostic_laps(laps)
    runs = split_runs(laps)

    codes = _compounds_run(runs)
    single = _compound_full_name(codes[0]) if len(codes) == 1 else None
    meta = Meta(
        # No placeholders on any of the three. The event screen already blocks
        # a save without a car or a track, so a fallback here only defeats the
        # validator's own refusal: "unknown" is not a GT7 car, and `"A"` is a
        # positive, well-formed claim that the 296-byte base format was
        # captured. Per contract §2 that claim is what tells a reader whether
        # an absent extended channel was not measured or not offered, so a
        # session GT7 never streamed to would have declared every one of them
        # physically unavailable.
        car=event["car_name"],
        circuit=_circuit_name(event),
        date=(session["started_at"] or "")[:10],
        session_type=session["kind"],
        packet=session["packet_format"],
        car_category=_car_category(session["car_category"]),
        # **The session's own stamp first.** It is the only one of the three
        # that is a property of when the measurement was actually taken, and
        # an event can straddle a patch: event 1 holds 44 sessions spanning
        # 11 to 21 Aug 2026 and 1.71 landed on the 20th, so its single event
        # value is wrong for one side of it whichever way it is set. The
        # event's declaration is next, for a run filed under a version no
        # longer installed, and the app's setting last.
        game_version=(_session_field(session, "game_version")
                      or event["game_version"] or game_version),
        practice_intent=_session_field(session, "practice_intent"),
        practice_mode=_session_field(session, "practice_mode"),
        rehearsal=bool(_session_field(session, "rehearsal")),
        # Only where one compound was run. Several runs on several compounds
        # is not a session with a compound, and voting on the most common tag
        # made a three-compound session read as a Racing Hard one - which is
        # the finding that nearly picked the race tyre.
        compound_front=single,
        compound_rear=single,
        compounds_run=[_compound_full_name(code) for code in codes] or None,
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
    # The **diagnostic** set, not the counted one. A lap with a spin in it is
    # out of the pace and fuel numbers and stays in the corner aggregates,
    # because the car is what spun.
    counted_with_frames = [_counted_lap(lap) for lap in diagnostic if lap.frames]
    # **The reference comes off the counted laps only**, even though the
    # aggregates span the diagnostic set. The reference is the floor every
    # `bottoming` flag is judged against, and an off or a spin compresses the
    # suspension below anything a clean lap reaches - so one incident lap
    # silently lowered the floor for the whole session and the flag stopped
    # firing on the laps it was meant to describe. On the Monza event laps 26,
    # 74 and 79 were setting it.
    reference_laps = [_counted_lap(lap) for lap in counted if lap.frames]
    bottoming_ref = None
    bottoming_ref_source = None
    observed_min = None
    length_note = None
    if model is not None and counted_with_frames:
        meta.corner_model = model.as_meta()
        bottoming_ref = bottoming_reference(reference_laps, model)
        observed_min = observed_minimum(reference_laps)
        if bottoming_ref is not None:
            sheets = {lap.setup_sheet_id for lap in reference_laps}
            bottoming_ref_source = (
                f"peak compression per wheel over the straight-line frames "
                f"of the {len(reference_laps)} counted "
                f"lap{'' if len(reference_laps) == 1 else 's'} that carried "
                f"them, keyed on the setup sheet each lap ran "
                f"({len(sheets)} sheet{'' if len(sheets) == 1 else 's'}). "
                f"**susp_mm is travel, not height** - measured 17 Aug 2026, "
                f"body height falls 61 to 50 mm from 120 to 260 km/h while "
                f"every susp_mm rises - so the bottoming end of the trace is "
                f"the maximum. Laps with an off or a spin are held out: they "
                f"reach compressions no clean lap does and would set the "
                f"limit every bottoming flag is judged against. "
                f"observedMinHeightMm is the raw minimum of the same channel, "
                f"which is the EXTENDED end and a measurement rather than "
                f"this inference")
        # **The packet's own wheelbase where the session recorded one.**
        # `understeer-mid`'s expected yaw goes as 1/wheelbase, and with
        # nothing stored every car was judged against the RSR's 2.516 m -
        # about 4% high on the Huracan, biased toward reporting understeer on
        # a flag the driver had contradicted four sessions running. Sessions
        # recorded before the column existed read null and fall back to the
        # stated default, which the thresholds block already labels `assumed`.
        # **Held out before the aggregate, and SAID.** `length_gate` refuses a
        # lap whose integrated distance disagrees with the session median: a
        # corner window is a fixed distance range, so such a lap's windows are
        # not on the same road. Measured at 8-12% of clean laps. The note is
        # not optional - an exclusion nobody is told about is worse than no
        # exclusion.
        gate = length_gate(counted_with_frames)
        length_note = " ".join(part for part in (_anchor_note(anchor),
                                                 gate.as_note()) if part)
        corners = aggregate_corners(
            model, gate.kept, bottoming_ref,
            wheelbase_m=_session_field(session, "wheelbase_m"),
            # **Declared, because GT7 broadcasts no drivetrain channel and
            # the torque vectors that might have inferred one read zero on
            # this stream.** Without it `wheelspin` watches all four wheels,
            # so a front wheel lifted over a kerb under throttle counts: at
            # Watkins T2 that was 15 laps of 17 with a kerb strike on all 17.
            # None where nobody has said and the catalogue does not carry the
            # car either, and the payload goes on disclosing that it is
            # watching all four.
            drivetrain=drivetrain)

    # **The setup is not in this payload, and that is deliberate.**
    #
    # The app no longer records what is in the car. The tune builder holds the
    # setup and the gearbox, issues changes directly, and the driver confirms
    # them against GT7's own settings screen - so the reader of this payload
    # already has the sheet, from the side that wrote it. Carrying a second
    # copy from here would be the thing the removal was for: a value in two
    # places becomes two values, and it had already happened twice on one car.
    #
    # What went with it is the rank-zero doubt gate. It refused an export
    # whose setup record could not be trusted, and there is no longer a setup
    # record to distrust. **The question it asked has not gone away** - it has
    # moved to the side that can actually answer it, which is the one holding
    # the sheet and the screenshot.
    #
    # `gearing` stays, and it is now the only channel that speaks about the
    # gearbox at all: the ratios are in the packet, so `fittedRatios` is
    # measured. With no sheet to compare against, `matchesSheet` is null - not
    # measured rather than agreeing - and `gearingConstantK` comes off the
    # derived rolling radius, which the payload's own note says reads high
    # through the unloaded tyre.
    gearing = gearing_export(counted)

    strategy = _strategy_section(store, event["id"])

    range_record = None
    if event["car_name"]:
        record = store.get_range_record(event["car_name"])
        if record is not None:
            range_record = record.as_export()

    all_notes = " ".join(part for part in (exclusion_note(laps),
                                           capacity_note, length_note,
                                           notes) if part)

    wear = wear_export(
        laps, calibrated_at_race_multiplier=calibrated_at_race_multiplier,
        race_multiplier=event["tyre_wear_mult"])

    return build_payload(
        meta,
        range_record=range_record,
        session=session_export(laps, fuel_capacity_l=fuel_capacity_l),
        laps=[lap_export(lap) for lap in laps],
        runs=runs_export(runs),
        corners=corners,
        wear=wear,
        gearing=gearing,
        strategy=strategy,
        derived=Derived(
            {**thresholds.as_export(
                drivetrain=drivetrain, drivetrain_source=drivetrain_source,
                wheelbase_m=_session_field(session, "wheelbase_m")),
             **incident_thresholds()},
            bottoming_ref_mm=bottoming_ref,
            bottoming_ref_source=bottoming_ref_source,
            observed_min_height_mm=observed_min,
            # Named, with what was seen on each. A lap dropped from the pace
            # numbers with no reason attached is indistinguishable from one
            # that was never driven, and the reader has to be able to tell an
            # excluded lap from a missing one.
            extra=({"incidents": incidents_export(incidents)}
                   if incidents else {})),
        notes=all_notes,
    )


def _section_from_plan(plan: dict) -> dict:
    """The export's strategy shape, built from a plan's own flat keys.

    For a plan authored outside the app, which has stints and stops and a
    binding constraint but no `export` block. Everything `Plan.as_export`
    derives from a `RaceInputs` it never had - the compound profiles, the
    crossover, the costed assumptions - is absent rather than invented: a
    handover's numbers came from somewhere else and guessing their provenance
    here would put the app's name on the engineer's arithmetic.
    """
    stints = [s for s in (plan.get("stints") or []) if isinstance(s, dict)]
    if not stints:
        return {}
    pit_laps = plan.get("pit_laps") or []
    return {
        "plan": {
            "stops": plan.get("stops"),
            "laps": sum(int(s.get("laps") or 0) for s in stints) or None,
            "stintLaps": [int(s.get("laps") or 0) for s in stints],
            "compounds": [s.get("compound") for s in stints],
            # Only the first stop travels - `pitLaps` is not in the contract's
            # key allow-list, and `to_json` refuses a payload carrying one.
            "pitLap": pit_laps[0] if pit_laps else None,
        },
        "bindingConstraint": plan.get("binding_constraint"),
        "compoundCrossover": None,
        "compoundProfiles": [],
    }


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
        # **A plan the app did not write has no `export` block**, because only
        # `Plan.as_export` makes one and a handover never goes through it. The
        # whole strategy section then vanished - the plan, its assumptions,
        # every call the engineer made and the outcome line - and `validate`
        # returned no problems, so a race run to a loaded plan exported
        # silently gutted. CLAUDE.md 5.5 requires the calls and the
        # assumptions behind them; this is the case that had neither.
        section = _section_from_plan(approved["plan"])
    if not section:
        return None

    assumptions = section.setdefault("assumptions", {})
    event = store.get_event(event_id)
    if event is not None:
        # Required: at 1 L/s against a 2.5 default this is the number that
        # decides the race, and a default standing in its place is unreadable.
        #
        # **What the plan was costed with wins.** The event column used to be
        # written over the top of it unconditionally, so a plan whose every
        # stop was costed at a measured 3.0 L/s exported the driver's typed
        # 1.0 beside it and the reader re-derived a 100 s stop for a plan that
        # assumed 33 s. The column is the fallback, not the answer, and it
        # says which of the two it is.
        rate, source = _refuel_rate(assumptions.get("refuelRateLps"), event)
        assumptions["refuelRateLps"] = rate
        assumptions["refuelRateSource"] = source
        assumptions["mandatoryStops"] = event["mandatory_stops"]

    # **What the plan expected to execute, beside what it executed.** Stored
    # with the plan rather than in the export's own schema, and reported here
    # through `outcome` - a free-text field the contract already defines for
    # exactly this - so nothing arrives that a reader would have to interpret
    # conservatively. See §10's `outcome`, and `race/expectations.py`.
    expects = approved["plan"].get("expects")

    calls = _calls_made(store, event_id)
    if calls:
        # The contract defines callsMade[] and the validator enforces
        # exactly that list, so the internal bookkeeping keys - `kind` and
        # `resolution` - stay out of the payload. They exist for the outcome
        # line below, which is where the audit reads them.
        #
        # **`verdict` had to be added HERE as well as to the entry, and it
        # was not** (critic pass 8): the entry carried it, this projection
        # dropped it, and nothing noticed because `kind` is dropped the same
        # way. A field added to `_calls_made` alone reaches no file. It also
        # needs `payload.KNOWN_KEYS` and EXPORT-CONTRACT §10 - three places,
        # and the validator REFUSES the whole payload if the first two
        # disagree, so a half-done job costs the driver the export.
        section["callsMade"] = [
            {key: value for key, value in call.items()
             if key in ("lap", "call", "reason", "accepted", "disposition",
                        "confidence", "verdict", "verdictDetail")}
            for call in calls]

    outcome = _outcome(store, event_id, calls, section, expects)
    if outcome:
        section["outcome"] = outcome
    return section


# The value `events.refuel_rate_lps` is created with. The column is
# `NOT NULL DEFAULT 2.5`, so it is never absent - which is why the validator's
# None test could never fire. Equal to it is not proof the driver never looked,
# but it is the state the app ships in, and it is the state that must not pass
# for a measurement.
REFUEL_RATE_DEFAULT = 2.5

PLAN_REFUEL_SOURCE = "as the plan was costed"
DECLARED_REFUEL_SOURCE = "driver-declared on the event page"
DEFAULT_REFUEL_SOURCE = "still the app default - not confirmed"
MISSING_REFUEL_SOURCE = "not entered"


def _refuel_rate(planned: float | None, event) -> tuple[float | None, str]:
    """The rate the stops were actually costed at, and where it came from."""
    if planned is not None:
        return planned, PLAN_REFUEL_SOURCE
    rate = event["refuel_rate_lps"]
    if rate is None:
        return None, MISSING_REFUEL_SOURCE
    return rate, (DEFAULT_REFUEL_SOURCE if rate == REFUEL_RATE_DEFAULT
                  else DECLARED_REFUEL_SOURCE)


def _outcome(store, event_id: int, calls: list[dict], section: dict,
             expects: dict | None = None) -> str:
    """What happened, from the race laps. Omitted when no race was run.

    Takes the full `_calls_made` list - with the internal `kind` and
    `resolution` keys still on it - rather than the contract-trimmed copy in
    the section, because the stay-out fold is found by its recorded kind.

    `expects` is what the plan said it would execute. **Where the race
    superseded it, both figures go out**: what the plan was built on and what
    it actually ran on, which is the whole audit value. Nothing about it is a
    new key - the contract's `outcome` is prose, and prose is where a
    comparison with its own sample counts and noise floor belongs.
    """
    # `hydrate=set()` - every reader below this is column-only:
    # `race_outcome`, `fuel_left_note` and `audit_line_from_laps`
    # never touch `.frames`. Checked, not assumed.
    race_laps = event_lap_inputs(store, event_id, "race",
                                 hydrate=set())
    if not race_laps:
        return ""
    plan = section.get("plan") or {}
    declined = sum(1 for call in calls if call.get("accepted") is False)
    # The lap the engineer stopped repeating an ignored box call and folded
    # to the driver's stay-out. Read off the revision's own recorded kind,
    # never inferred from the spoken text - a data key derived from a
    # display label is a defect this codebase has already paid for once.
    stay_out = next((call["lap"] for call in calls
                     if call.get("kind") == "stay-out"
                     and call.get("accepted")), None)
    text = race_outcome(
        race_laps,
        planned_stops=plan.get("stops"),
        planned_pit_laps=[plan["pitLap"]] if plan.get("pitLap") else None,
        binding_constraint=section.get("bindingConstraint"),
        declined_calls=declined,
        stay_out_lap=stay_out)
    fuel = fuel_left_note(race_laps)
    parts = [text, fuel, audit_line_from_laps(expects, race_laps)]
    return " ".join(part for part in parts if part).strip()


# **Which calls were ever a question.** `accepted` is only a fact about a call
# that asked something, and most calls do not: "Green, green, green.", "P2. 5
# to go." and "Chequered flag." are statements. Recording those as
# `accepted: false` is not a missing value, it is a fabricated claim that the
# driver refused them - and on the Watkins race it made all fourteen calls
# read as declined, which left the only feedback channel on the strategy
# engine saying nothing at all.
#
# CLAUDE.md rule 3: missing is null, never a substitute. So `accepted` is now
# null wherever the call was not an offer, and `disposition` carries what
# actually became of it.
_INSTRUCTION_KINDS = frozenset({"box-now", "box-soon"})
# How many laps after an instruction a stop still counts as acting on it. A
# "box next lap" obeyed is a pit lap on the very next crossing; two covers the
# in-lap arriving a lap later than the call named, which is the normal case
# for "box in 2".
#
# **Imported rather than restated**: `call_outcome` judges the same window
# live, and two constants for one window drift (critic pass 8).
from pitcrew.race.call_outcome import BOX_WINDOW_LAPS as _INSTRUCTION_WINDOW_LAPS  # noqa: E402,E501

DISPOSITION_INFORMATIONAL = "informational"
DISPOSITION_TAKEN = "taken"
DISPOSITION_NOT_TAKEN = "not-taken"
# An instruction the race never finished driving the window of. Not
# `not-taken`, which is a claim about the driver the laps do not support.
DISPOSITION_UNANSWERED = "unanswered"

# **The verdict's vocabulary, imported rather than restated.** `disposition`
# is derived from it where the race wrote one, so the two cannot drift into
# saying different things about one call (rule 13).
from pitcrew.race.call_outcome import ACTED as OUTCOME_ACTED  # noqa: E402
from pitcrew.race.call_outcome import NOT_ACTED as OUTCOME_NOT_ACTED  # noqa: E402


def _disposition(revision: dict, pit_laps: set[int]) -> tuple[str, bool | None]:
    """What became of one call, and whether `accepted` means anything for it.

    Returns `(disposition, accepted)`. `accepted` is None for everything that
    never asked a question - which is most of them.
    """
    plan = revision["plan"]
    resolution = plan.get("resolution")
    if resolution:
        # An offer that was resolved. The replan layer's own vocabulary -
        # accepted, kept, expired, superseded - travels unchanged rather than
        # being flattened into a bool that cannot hold four states.
        return resolution, bool(revision["accepted"])
    if plan.get("informational"):
        # Said, never asked. The path that records these passes
        # `accepted=False` because the column has no third state, and that
        # false is the absence of a question rather than a refusal.
        return DISPOSITION_INFORMATIONAL, None
    # **Inside the branch, not above it** (critic pass 8, fourth round).
    # Lifting it out was for the short-shift call, which `outcome_for` no
    # longer judges at all - the field it judged on is the app's own switch -
    # so `acted`/`not-acted` arise for the two box kinds and nothing else,
    # and the precedence of every other branch is left exactly as it was.
    verdict = revision.get("verdict")
    if plan.get("kind") in _INSTRUCTION_KINDS:
        if verdict == OUTCOME_ACTED:
            return DISPOSITION_TAKEN, None
        if verdict == OUTCOME_NOT_ACTED:
            return DISPOSITION_NOT_TAKEN, None
        # **Derived, and from the laps rather than from an answer.** An
        # instruction is not offered and is never answered; what says whether
        # it was followed is whether a pit lap turned up. Stated here rather
        # than inferred by a reader - and reached only where the race wrote
        # no verdict, which since 1.9 means a row from before it.
        if verdict:
            # **`cannot-tell` means the window was never fully driven in
            # that race**, so the same session cannot have supplied a stop
            # in it - and the fallback's `pit_laps` are pooled over every
            # race session of the event, renumbered continuously across
            # runs, so a `taken` from here could only ever come from another
            # run's lap in another numbering. It said `taken` beside
            # `verdict: cannot-tell` in one object (critic pass 8, second
            # round): rule 13 reappearing one line below where it was fixed.
            # A row that WAS judged and declined to claim is not overruled.
            return DISPOSITION_UNANSWERED, None
        lap = revision["lap_num"]
        if lap is None:
            return DISPOSITION_NOT_TAKEN, None
        taken = any(lap <= pit <= lap + _INSTRUCTION_WINDOW_LAPS
                    for pit in pit_laps)
        return (DISPOSITION_TAKEN if taken else DISPOSITION_NOT_TAKEN), None
    if plan.get("kind"):
        return DISPOSITION_INFORMATIONAL, None
    # **No kind at all is a record from before the marker existed**, and there
    # the stored boolean is the only thing that ever meant anything - a plan
    # offered and refused is evidence about the model, so it keeps saying so.
    return ("accepted" if revision["accepted"] else "declined",
            bool(revision["accepted"]))


def _calls_made(store, event_id: int) -> list[dict]:
    """Every call, including the ones declined.

    A plan offered and refused is evidence about the model; dropping it makes
    the model look better than it was.
    """
    # `hydrate=set()`: two columns are read here, `lap_num` and
    # `is_pit_lap`, and the default decoded every race lap's blob to reach
    # them. Measured 3.773 s against 0.003 s, payload byte-identical.
    pit_laps = {lap.lap_num
                for lap in event_lap_inputs(store, event_id, "race",
                                            hydrate=set())
                if lap.is_pit_lap and lap.lap_num is not None}
    calls: list[dict] = []
    for run in store.list_race_runs(event_id):
        for revision in store.list_revisions(run["id"]):
            disposition, accepted = _disposition(revision, pit_laps)
            entry = {
                "lap": revision["lap_num"],
                "call": revision["reason"],
                "accepted": accepted,
                "disposition": disposition,
                "confidence": revision["plan"].get("confidence", "unstated"),
            }
            # The structured kind, where the revision recorded one. It is
            # what lets the outcome find the stay-out fold without parsing
            # the spoken sentence back apart.
            if revision["plan"].get("kind"):
                entry["kind"] = revision["plan"]["kind"]
            # How an offer left the desk - accepted, explicitly kept,
            # expired unanswered, superseded - so the audit can tell a
            # refusal from a question the driver never answered.
            if revision["plan"].get("resolution"):
                entry["resolution"] = revision["plan"]["resolution"]
            # **What the driver then did**, judged as the laps came in
            # (`race/call_outcome`, written by the controller). Absent where
            # the race was recorded before verdicts were kept.
            if revision.get("verdict"):
                entry["verdict"] = revision["verdict"]
                entry["verdictDetail"] = revision.get("verdict_detail")
            calls.append(entry)
    return calls


def _compound_full_name(code: str | None) -> str | None:
    """"RM" -> "Racing Medium". The contract wants the full GT7 name."""
    if not code:
        return None
    compound = get_by_code(code)
    return compound.name if compound else code


def _circuit_name(event: dict) -> str:
    track = event["track"] or ""
    layout = event["layout"]
    return f"{track} ({layout})" if layout else track
