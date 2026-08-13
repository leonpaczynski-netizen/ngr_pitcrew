"""Turning recorded practice into strategy inputs, with provenance attached.

The screen renders each input in the register it came from — telemetry in
stencil, driver-entered in crayon, the app's own assumptions struck — so the
driver can see at a glance which parts of the plan rest on measurement and
which rest on a guess. That is the difference between a plan he can trust
under pressure and one he cannot.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from pitcrew.analysis.runs import split_runs
from pitcrew.analysis.session import LapInput, counted_laps, green_lap_reference_ms
from pitcrew.analysis.wear import wear_per_lap as wear_rate
from pitcrew.analysis.wear import wear_rate_by_compound
from pitcrew.analysis.tyre_window import qualification, window_by_compound
from pitcrew.strategy.model import (
    FUEL_WEIGHT_S_PER_L_PER_LAP,
    PIT_DEAD_TIME_S,
    SOURCE_DECLARED,
    SOURCE_MEASURED,
    CompoundProfile,
    RaceInputs,
    laps_from_minutes,
)

MEASURED = "measured"      # off the telemetry stream
DECLARED = "declared"      # the driver entered it
ASSUMED = "assumed"        # the app's own working figure
MISSING = "missing"        # not known, and not invented


@dataclass(frozen=True)
class Evidence:
    label: str
    value: str
    source: str
    note: str = ""


# How many laps per compound get their frames decoded for the temperature
# window. A lap's mean surface temperature barely moves lap to lap, so a
# handful is a real sample rather than a compromise - and the alternative is
# not free: one lap's blob is ~1.6 MiB and costs ~65 ms to decode, so a
# three-evening practice event would freeze the Strategy screen for seconds,
# and freeze it again when the race is armed.
#
# The cap is never silent. `lapsSampled` travels in the window payload and on
# the export, so the sample size is always visible next to the conclusion.
WINDOW_SAMPLE_LAPS = 6


def _lap_inputs(store, event_id: int) -> list[LapInput]:
    """Every practice lap, with frames on only the laps that need them.

    Frames are decoded for the temperature window and nothing else here, so
    only the laps that window looks at are hydrated - the most recent few on
    each compound, which are also the most representative: latest setup, track
    at its most rubbered in.
    """
    rows = store.list_event_laps(event_id, "practice")
    wanted = _laps_to_hydrate(rows)
    return [
        LapInput(
            frames=_frames_for(store, row["id"]) if row["id"] in wanted else None,
            lap_num=row["lap_num"],
            lap_time_ms=row["lap_time_ms"],
            fuel_start=row["fuel_start"],
            fuel_end=row["fuel_end"],
            compound=row["compound"],
            is_pit_lap=bool(row["is_pit_lap"]),
            is_out_lap=bool(row["is_out_lap"]),
            excluded=bool(row["excluded"]),
            exclusion_reason=row["exclusion_reason"],
            wear_fl=row["wear_fl"],
            wear_fr=row["wear_fr"],
            wear_rl=row["wear_rl"],
            wear_rr=row["wear_rr"],
        )
        for row in rows
    ]


def _fuel_capacity(store, event_id: int) -> float | None:
    for session in store.list_sessions(event_id, "practice"):
        if session["fuel_capacity_l"] is not None:
            return session["fuel_capacity_l"]
    return None


def _laps_to_hydrate(rows) -> set[int]:
    """Lap ids worth decoding: the last few counted laps on each compound."""
    by_compound: dict[str, list[int]] = {}
    for row in rows:
        counted = not (row["excluded"] or row["is_out_lap"] or row["is_pit_lap"])
        if row["compound"] and counted:
            by_compound.setdefault(row["compound"], []).append(row["id"])
    wanted: set[int] = set()
    for lap_ids in by_compound.values():
        wanted.update(lap_ids[-WINDOW_SAMPLE_LAPS:])
    return wanted


def _frames_for(store, lap_id: int) -> list[dict] | None:
    stored = store.get_lap_frames(lap_id)
    return stored["frames"] if stored else None


def reference_compound(counted: list[LapInput]) -> str | None:
    """The compound everything else is measured against: the most-run one.

    Ties are broken by which ran first, because the opening stint is the
    baseline the rest of the day was compared against by the driver too.

    The tie-break is not decoration. This was `max(set(tagged), key=count)`,
    and iterating a **set** of strings means the winner of a tie depends on
    string hash randomisation - a different reference compound per process,
    and with it a different sign on every pace delta in the table. Two equal
    stints on two compounds is the *normal* shape of a comparison test, so the
    tie was the common case rather than the edge one.
    """
    order: dict[str, int] = {}
    counts: dict[str, int] = {}
    for position, lap in enumerate(counted):
        if not lap.compound:
            continue
        counts[lap.compound] = counts.get(lap.compound, 0) + 1
        order.setdefault(lap.compound, position)
    if not counts:
        return None
    return min(counts, key=lambda code: (-counts[code], order[code]))


def compound_profiles(laps: list[LapInput],
                      reference: str | None) -> dict[str, CompoundProfile]:
    """What each compound costs and lasts, measured where practice ran it.

    Pace is the median counted lap on that compound against the median on the
    reference — median, not mean, so one scruffy lap does not decide which
    tyre the race is run on. Wear is the rate measured over the laps each set
    actually ran.

    A compound the driver has declared available but never run gets **no
    profile at all** rather than an invented one. `RaceInputs.profile_for`
    then falls back to the reference's rate and labels it `assumed`, so the
    plan can still be costed but never claims to have been measured.
    """
    counted = counted_laps(laps)
    by_compound: dict[str, list[LapInput]] = {}
    for lap in counted:
        if lap.compound:
            by_compound.setdefault(lap.compound, []).append(lap)
    if not by_compound:
        return {}

    reference_laps = by_compound.get(reference or "")
    reference_ms = (median([lap.lap_time_ms for lap in reference_laps])
                    if reference_laps else None)
    rates = wear_rate_by_compound(laps)
    windows = window_by_compound(laps)
    longest = longest_stint_by_compound(laps)

    profiles: dict[str, CompoundProfile] = {}
    for code, on_this in by_compound.items():
        pace_delta = 0.0
        if reference_ms and code != reference:
            pace_delta = (median([lap.lap_time_ms for lap in on_this])
                          - reference_ms) / 1000.0
        rate = rates.get(code)
        window = windows.get(code)
        profiles[code] = CompoundProfile(
            code=code,
            pace_delta_s=round(pace_delta, 3),
            wear_per_lap=rate["wearPerLap"] if rate else None,
            # Measured means measured: a compound run in practice with no
            # gauge reading has a pace we know and a wear rate we do not, and
            # it is the wear rate that sets the stint. A rate that exists but
            # rests on an assumed fresh set is not measured either.
            source=(SOURCE_MEASURED
                    if rate and rate.get("wearPerLap") is not None
                    else SOURCE_DECLARED),
            laps_measured=len(on_this),
            # The runs that produced a rate, not the runs on the compound: a
            # compound run three times and read once is one measurement.
            stints_measured=rate["stintsMeasured"] if rate else 0,
            # What has actually been run on it, so a stint is never planned
            # longer than one that has been completed.
            longest_stint_laps=longest.get(code, 0),
            window=window,
            # The figures above stay exactly as measured. This says how far
            # they can be trusted, which is a different claim.
            window_note=qualification(code, window),
        )
    return profiles


def _extra_time_s(event) -> float | None:
    """GT7's allowance for finishing the lap the clock expired on."""
    value = event["extra_time_s"] if "extra_time_s" in event.keys() else None
    return None if value is None else float(value)


def _timed_race_note(inputs: RaceInputs) -> str:
    """What the clock means, in the terms the plan is actually bounded by."""
    ceiling = inputs.max_duration_s
    if ceiling is None:
        return "converted from race minutes at the reference lap"
    minutes, seconds = divmod(ceiling, 60)
    return (f"the lap count follows from the stops, not the other way round - "
            f"the flag falls at {inputs.race_minutes:g} min and the race can "
            f"last at most {int(minutes)}:{seconds:04.1f}")


def longest_stint_by_compound(laps: list[LapInput]) -> dict[str, int]:
    """The longest single run on each compound, in laps.

    Per run rather than per compound: three four-lap runs on the soft say
    nothing about a five-lap stint, however many laps of it there are in
    total.
    """
    longest: dict[str, int] = {}
    for run in split_runs(laps):
        code = run.compound
        if not code:
            continue
        # Every lap the set turned, not only the counted ones. An out-lap and
        # a lap struck for a spin both wore the tyre exactly as much as a
        # clean one; excluding them would say a fifteen-lap run proved
        # thirteen, and cost a stop for nothing.
        longest[code] = max(longest.get(code, 0), len(run.laps))
    return longest


def build_inputs(store, event_id: int) -> tuple[RaceInputs, list[Evidence]]:
    """Assemble the model's inputs from the event and its practice laps."""
    event = store.get_event(event_id)
    if event is None:
        raise ValueError(f"no event with id {event_id}")

    laps = _lap_inputs(store, event_id)
    counted = counted_laps(laps)

    burns = [lap.fuel_start - lap.fuel_end for lap in counted
             if lap.fuel_start > lap.fuel_end]
    fuel_per_lap = round(median(burns), 3) if burns else None
    reference_ms = green_lap_reference_ms(laps)
    wear = wear_rate(laps)
    capacity = _fuel_capacity(store, event_id)

    # The compound the evidence came from. Stints default to it, because a
    # wear rate measured on one compound does not describe another.
    evidence_compound = reference_compound(counted)
    profiles = compound_profiles(laps, evidence_compound)

    # For a timed race the stored figure is minutes, not laps. The lap count
    # is only a starting estimate: what the race actually covers depends on
    # how many times the car stops, and the model works that out per plan.
    timed = event["race_type"] == "time"
    race_minutes = float(event["race_laps"] or 0) if timed else None
    race_laps = event["race_laps"] or 0
    if timed and reference_ms:
        race_laps = laps_from_minutes(race_minutes or 0, reference_ms)

    inputs = RaceInputs(
        race_laps=race_laps,
        race_minutes=race_minutes,
        extra_time_s=_extra_time_s(event),
        lap_time_ms=reference_ms or 0,
        fuel_per_lap_l=fuel_per_lap,
        fuel_capacity_l=capacity,
        refuel_rate_lps=event["refuel_rate_lps"],
        pit_loss_s=event["pit_loss_secs"],
        wear_per_lap=wear,
        mandatory_stops=event["mandatory_stops"] or 0,
        available_compounds=tuple(event["available_compounds"]),
        required_compounds=tuple(event["required_compounds"]),
        evidence_compound=evidence_compound,
        compound_profiles=profiles,
    )

    evidence = [
        Evidence("Race length",
                 (f"{race_laps} laps" if not timed
                  else f"{race_minutes:g} min, about {race_laps} laps"),
                 DECLARED if not timed else ASSUMED,
                 "" if not timed else _timed_race_note(inputs)),
        Evidence("Reference lap",
                 _lap_time(reference_ms), MEASURED if reference_ms else MISSING,
                 f"fastest of the first counted laps, {len(counted)} counted"
                 if reference_ms else "run a practice lap"),
        Evidence("Fuel per lap",
                 f"{fuel_per_lap:.2f} L" if fuel_per_lap else "—",
                 MEASURED if fuel_per_lap else MISSING,
                 f"median of {len(burns)} laps" if burns else "no fuel burn recorded"),
        Evidence("Fuel capacity",
                 f"{capacity:.0f} L" if capacity is not None else "—",
                 MEASURED if capacity is not None else MISSING,
                 "from the stream" if capacity is not None else ""),
        Evidence("Tyre wear",
                 f"{wear:.1%} per lap" if wear else "—",
                 DECLARED if wear else MISSING,
                 "from your gauge reading" if wear
                 else "read the in-game gauge and enter it on a practice lap"),
        Evidence("Evidence compound", evidence_compound or "—",
                 DECLARED if evidence_compound else MISSING,
                 "wear and fuel describe this compound only"
                 if evidence_compound else "tag your practice laps"),
        Evidence("Compounds compared", _compounds_compared(profiles),
                 MEASURED if _measured_count(profiles) > 1 else MISSING,
                 _compound_note(profiles, event["available_compounds"])),
        Evidence("Tyre window", _window_value(profiles),
                 _window_source(profiles), _window_note(profiles)),
        Evidence("Pit loss", f"{event['pit_loss_secs']:.1f} s", DECLARED,
                 "a track constant"),
        Evidence("Pit dead time", f"{PIT_DEAD_TIME_S:.1f} s", ASSUMED,
                 "before refuelling begins"),
        Evidence("Refuel rate", f"{event['refuel_rate_lps']:.2f} L/s", DECLARED),
        Evidence("Fuel weight",
                 f"{FUEL_WEIGHT_S_PER_L_PER_LAP:.3f} s/L/lap", ASSUMED,
                 "derived, not measured - overwrite it if you measure it"),
    ]
    return inputs, evidence


def _measured_count(profiles: dict[str, CompoundProfile]) -> int:
    return sum(1 for p in profiles.values() if p.is_measured)


def _compounds_compared(profiles: dict[str, CompoundProfile]) -> str:
    measured = sorted(p.code for p in profiles.values() if p.is_measured)
    return ", ".join(measured) if measured else "—"


def _compound_note(profiles: dict[str, CompoundProfile],
                   available: list[str]) -> str:
    """Say plainly whether the crossover question can be answered yet.

    Comparing compounds on total race time only means something when more than
    one has a measured wear rate. With one, every alternative is the reference
    rate wearing a different name, and the comparison would return the answer
    it was given.
    """
    measured = _measured_count(profiles)
    if measured == 0:
        return ("no compound has a measured wear rate - read the gauge at the "
                "end of a stint")
    if measured == 1:
        untried = [code for code in available
                   if code not in profiles or not profiles[code].is_measured]
        if untried:
            return (f"only one measured, so {', '.join(sorted(untried))} "
                    f"cannot be compared on its own merits - run a stint on "
                    f"one of them")
        return "only one compound measured"
    return (f"{measured} compounds measured, so the harder-tyre call rests on "
            f"evidence rather than on the reference rate")


def _windowed(profiles: dict[str, CompoundProfile]) -> list[CompoundProfile]:
    """Compounds whose laps carried a temperature at all."""
    return [p for p in profiles.values() if p.window]


def _window_value(profiles: dict[str, CompoundProfile]) -> str:
    """Each compound and the band it actually ran in."""
    measured = _windowed(profiles)
    if not measured:
        return "—"
    return " · ".join(f"{p.code} {p.window['band']}"
                      for p in sorted(measured, key=lambda p: p.code))


def _window_source(profiles: dict[str, CompoundProfile]) -> str:
    """Measured off the stream, or nothing captured at all.

    Never ASSUMED: this figure is either a real temperature or it is absent.
    """
    return MEASURED if _windowed(profiles) else MISSING


def _window_note(profiles: dict[str, CompoundProfile]) -> str:
    outside = [p for p in profiles.values() if p.window_note]
    if not _windowed(profiles):
        return ("no tyre temperature captured, so no compound's evidence can "
                "be checked against its window")
    if not outside:
        return ("every compound ran in its window, so the pace and wear above "
                "describe the compounds rather than the conditions")
    codes = ", ".join(sorted(p.code for p in outside))
    return (f"{codes} ran outside the window - the pace and wear measured "
            f"there describe the conditions as much as the compound")


def _lap_time(ms: int | None) -> str:
    if not ms:
        return "—"
    minutes, remainder = divmod(ms, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"
