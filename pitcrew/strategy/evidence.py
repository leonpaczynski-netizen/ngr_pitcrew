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

from pitcrew.analysis.daylight import coverage, sessions_to_run
from pitcrew.analysis.gameclock import (
    practice_clock_warning,
    race_span,
    read_clock,
)
from pitcrew.analysis.refuel import refuel_evidence
from pitcrew.analysis.resolve import circuit_key
from pitcrew.strategy.model import is_wet_compound
from pitcrew.analysis.recency import weighted
from pitcrew.analysis.modes import find_split
from pitcrew.analysis.version import prefer_current
from pitcrew.analysis.runs import split_runs
from pitcrew.analysis.weather import wet_evidence
from pitcrew.analysis.session import LapInput, counted_laps, reference_pace_ms
from pitcrew.analysis.wear import wear_per_lap as wear_rate
from pitcrew.analysis.wear import wear_rate_by_compound
from pitcrew.analysis.tyre_window import qualification, window_by_compound
from pitcrew.strategy.model import (
    FUEL_WEIGHT_S_PER_L_PER_LAP,
    PIT_DEAD_TIME_S,
    PIT_LOSS_DECLARED,
    SOURCE_DECLARED,
    SOURCE_MEASURED,
    CompoundProfile,
    RaceInputs,
    burn_at_fuel_map,
    consecutive_sd,
    laps_from_minutes,
    timed_race_stop_s,
)

MEASURED = "measured"      # off the telemetry stream
DECLARED = "declared"      # the driver entered it
ASSUMED = "assumed"        # the app's own working figure
MISSING = "missing"        # not known, and not invented


# How many laps on the installed version before the plan is built on them
# alone. One lap is a lap; it is not a stint, a fuel burn or a degradation
# rate. Below this the plan falls back to pre-patch evidence and says so,
# which is more useful than a set too small for any downstream check to accept.
MIN_LAPS_ON_VERSION = 3


def _planning_version(store, event) -> str | None:
    """The GT7 version this plan is being built for.

    The event's own declaration where it has one - a round being prepared
    under a version that is not the one installed - and the installed version
    otherwise, because that is what the car will be racing on.
    """
    declared = (event or {}).get("game_version")
    if declared:
        return declared
    from pitcrew import settings as _settings
    try:
        return _settings.load(store).game_version or None
    except Exception:                                        # noqa: BLE001
        return None


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


def _refuelled(row) -> bool:
    """Whether this lap's tank ended fuller than it started.

    The one cheap, exact test for a lap that carries a fill, and it reads off
    the lap row rather than the frames - which is the point, because deciding
    which laps to decode is what starved the measurement in the first place.

    **It does not consult `is_pit_lap`.** On the owner's database that flag is
    0 on every lap ever recorded, refuel laps included, so anything gated on
    it measures nothing.
    """
    keys = row.keys() if hasattr(row, "keys") else ()
    added = row["fuel_added_l"] if "fuel_added_l" in keys else None
    if added:
        return True
    start = row["fuel_start"] if "fuel_start" in keys else None
    end = row["fuel_end"] if "fuel_end" in keys else None
    return start is not None and end is not None and end > start


def _lap_inputs(store, event_id: int) -> list[LapInput]:
    """Every practice lap, with frames on only the laps that need them.

    **The same loader the export uses**, so the plan and the payload describe
    one session. This used to be a second implementation, and it dropped the
    session id and the continuous lap numbering: every lap of every evening
    read as one session with lap numbers restarting at 1 inside it. That is
    invisible until something depends on it - and the compound comparison
    depends on it entirely, because two compounds run on two evenings compare
    the evenings.

    Two things need frames, and they need **different laps**. The temperature
    window wants the most recent few on each compound. The refuel rate wants
    the lap the car took fuel on - and that lap fails every test the window
    applies, which is how `analysis/refuel.py` came to be structurally
    guaranteed to receive no frames on the only lap that carries what it
    measures.
    """
    from pitcrew.export.build import evidence_lap_inputs

    # **Practice and any rehearsal race.** Not the league race: that is
    # the thing being planned for, and a plan built on the race it is
    # planning is not a plan.
    rows = store.list_evidence_laps(event_id)
    return evidence_lap_inputs(store, event_id,
                               hydrate=_laps_to_hydrate(rows))


def _fuel_capacity(store, event_id: int) -> float | None:
    for kind in ("practice", "race"):
        for session in store.list_sessions(event_id, kind):
            if session["fuel_capacity_l"] is not None:
                return session["fuel_capacity_l"]
    return None


def _laps_to_hydrate(rows) -> set[int]:
    """Lap ids worth decoding: the temperature window's, and every refuel.

    The window's three filters - counted, compound-tagged, last few per
    compound - were written for the window and then used as the *only*
    hydration for the whole strategy path. **All three exclude a refuel lap.**
    It is a pit lap by definition, it is often untagged, and even where it
    survives both it is an early lap in the session and the last-six cap drops
    it: on the owner's own 26-lap rehearsal the fill is lap 14 and the cap
    keeps 21 to 26. So the rate came back `declared` forever, every stop was
    costed at the typed figure, and that figure decides the stop count.

    The window keeps its cap - a lap's blob is ~1.6 MiB and ~65 ms to decode,
    and mean surface temperature barely moves lap to lap. A fill is rare and
    is found from the lap row's own fuel columns, so this adds a decode per
    stop and not per lap.
    """
    by_compound: dict[str, list[int]] = {}
    wanted: set[int] = set()
    for row in rows:
        counted = not (row["excluded"] or row["is_out_lap"] or row["is_pit_lap"])
        if row["compound"] and counted:
            by_compound.setdefault(row["compound"], []).append(row["id"])
        if _refuelled(row):
            wanted.add(row["id"])
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

    comparable = comparable_pace(laps, reference)

    profiles: dict[str, CompoundProfile] = {}
    for code, on_this in by_compound.items():
        pace = comparable.get(code)
        rate = rates.get(code)
        window = windows.get(code)
        profiles[code] = CompoundProfile(
            code=code,
            pace_delta_s=round(pace["deltaS"], 3) if pace else 0.0,
            pace_known=bool(pace),
            pace_basis=(pace["basis"] if pace
                        else comparable_pace_gap(laps, reference, code)),
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
            # Carried through rather than collapsed into `source`, which is
            # MEASURED for any rate at all. What sets a stint is whether the
            # gauge was read twice inside one run, and how deep it watched.
            wear_confidence=(rate.get("confidence") if rate else None),
            deepest_observed_frac=(rate.get("deepestObservedFrac")
                                   if rate else None),
        )
    return profiles


def _reading_from(stored: dict | None):
    """A stored measurement, back in the shape the span maths wants."""
    if stored is None:
        return None
    from pitcrew.analysis.gameclock import ClockReading

    return ClockReading(
        multiplier=stored["multiplier"], start_hour=stored["start_hour"],
        end_hour=None, stopped_at_hour=stored["stops_at_hour"],
        laps_sampled=stored["laps_sampled"], note="")


def _rain_possible(event) -> bool | None:
    value = event["rain_possible"] if "rain_possible" in event.keys() else None
    return None if value is None else bool(value)


def _weather_value(weather: dict) -> str:
    if weather["canRain"] is False:
        return "rain impossible"
    if weather["canRain"] is None:
        return "not declared"
    return ("rain possible, no wet running"
            if not weather.get("wetLaps") else "rain possible, wets run")


def _event_float(event, key: str) -> float | None:
    value = event[key] if key in event.keys() else None
    return None if value is None else float(value)


def _event_int(event, key: str) -> int | None:
    value = event[key] if key in event.keys() else None
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        # A value that is not a number is not a declaration. Rule 3: nothing
        # said, rather than a plausible 1.
        return None


def _evidence_fuel_map(laps) -> int | None:
    """The fuel map the counted laps were run on, where they agree on one.

    **Disagreement is not an average.** Two maps across the evidence is two
    populations 15-50% apart in burn, and a single figure over both is a
    number that belongs to neither - the same argument as the beep's two
    columns (`expectations.FUEL_BASIS_COLUMN`). Where they disagree this
    returns None, the burn is not re-costed, and the plan's evidence row says
    the maps were mixed. Where nobody recorded one - which is every lap since
    session 83 - it returns None too, and the row says that instead.
    """
    declared = {lap.fuel_map for lap in laps
                if getattr(lap, "fuel_map", None) is not None}
    return declared.pop() if len(declared) == 1 else None


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


# A compound comparison is only a comparison if the laps are alike. Laps this
# far into a run carry a materially different tank; laps this far into a set
# carry a materially different tyre. Both dwarf the difference between two
# racing compounds, so a comparison that ignores them is measuring the session
# rather than the rubber.
PACE_MAX_TYRE_AGE = 5           # laps into the set
PACE_FUEL_BAND_L = 15.0         # spread of starting fuel across compared laps
PACE_MIN_LAPS = 3               # per compound, before a comparison is offered


def lap_time_of(lap: LapInput) -> int | None:
    """The whole lap - the timing every compound comparison used before 5.22."""
    return lap.lap_time_ms


def _pace_candidates(laps: list[LapInput],
                     timing=lap_time_of) -> dict[str, list[LapInput]]:
    """Counted laps young enough on their set to describe the compound.

    `timing` is what is being compared - the lap, or one sector (plan row
    5.22). **The tyre age is counted over every lap of the run before it is
    applied**, so a lap whose sector was refused still ages the set.
    """
    out: dict[str, list[LapInput]] = {}
    for run in split_runs(laps):
        for age, lap in enumerate(run.laps):
            if (lap.counted and lap.compound and age < PACE_MAX_TYRE_AGE
                    and timing(lap) is not None):
                out.setdefault(lap.compound, []).append(lap)
    return out


def session_of(lap: LapInput):
    """The unit a strategy compound comparison must sit inside."""
    return lap.session_id


def comparable_groups(laps: list[LapInput], reference: str | None,
                      timing=lap_time_of,
                      group_of=session_of) -> dict[object, dict[str, list[LapInput]]]:
    """Every group that holds a like-for-like compound comparison.

    **The one expression of "comparable"** (CLAUDE.md rule 12): the strategy
    delta, the practice report's lap and sector gaps and their spreads are all
    read off these pools. `group_of` is the unit the laps must share -
    the session for strategy; one evening of back-to-back runs for the
    practice report (plan row 5.22), which says so wherever it prints a gap.
    The lap and sector pools are drawn separately, through their own `timing`;
    they hold the same laps because capture stores a lap's sectors all three or
    none (`lap_sectors`), not because this function forces it.

    Each value holds, per compound, the laps inside the reference's fuel band;
    a group is kept only when the reference and one other compound both have
    `PACE_MIN_LAPS` there.
    """
    candidates = _pace_candidates(laps, timing)
    if not reference or reference not in candidates:
        return {}

    by_group: dict[object, dict[str, list[LapInput]]] = {}
    for code, pool in candidates.items():
        for lap in pool:
            by_group.setdefault(group_of(lap), {}).setdefault(
                code, []).append(lap)

    out: dict[object, dict[str, list[LapInput]]] = {}
    for key, pools in by_group.items():
        reference_laps = pools.get(reference, [])
        if len(reference_laps) < PACE_MIN_LAPS or len(pools) < 2:
            continue
        fuels = [lap.fuel_start for lap in reference_laps]
        low = min(fuels) - PACE_FUEL_BAND_L
        high = max(fuels) + PACE_FUEL_BAND_L

        found: dict[str, list[LapInput]] = {}
        for code, pool in pools.items():
            matched = [lap for lap in pool if low <= lap.fuel_start <= high]
            if len(matched) >= PACE_MIN_LAPS:
                found[code] = matched
        if len(found) > 1:
            out[key] = found
    return out


def comparable_pools(laps: list[LapInput], reference: str | None,
                     timing=lap_time_of) -> dict[str, list[LapInput]]:
    """The one session's pools `comparable_pace` compares.

    The session that compared the most compounds wins; on a tie, the first
    such session in the order `comparable_groups` meets them, which is the
    order the candidate laps are met compound by compound - not necessarily
    the earliest session. A comparison of three in one run says more than two
    in another.
    """
    best: dict[str, list[LapInput]] = {}
    for pools in comparable_groups(laps, reference, timing).values():
        if len(pools) > len(best):
            best = pools
    return best


def comparable_pace(laps: list[LapInput],
                    reference: str | None) -> dict[str, dict]:
    """Seconds per lap against the reference, on like-for-like laps only.

    **The old figure was the median lap time on each compound, whole stop.**
    At Monza that made Racing Medium 0.92 s/lap quicker than Racing Hard and
    Racing Soft only 0.56 s - the medium beating the soft, which is not a thing
    tyres do. It was not measuring tyres. The three compounds ran in three
    separate sessions across two evenings, so the difference between their
    medians carried the fuel load, the tyre age, the track evolution and the
    driver's own warm-up, and every one of those is larger than the gap between
    two racing compounds.

    Three conditions, and all of them have to hold:

    * **the same session** - a compound run on Tuesday against one run on
      Wednesday compares the evenings, not the tyres;
    * **young on the set**, so the comparison is of compounds and not of wear;
    * **one band of starting fuel**, so it is not of tank weight.

    Where they cannot all be met the comparison is **not made**. A refusal that
    names the run which would fix it is worth more than a number that reads as
    measured - and at Monza it is the only honest output, because no two
    compounds ever shared a session.
    """
    pools = comparable_pools(laps, reference)
    if not pools:
        return {}
    # The yardstick is the reference's laps INSIDE its own fuel band, which is
    # every one of them - the band is drawn around them.
    reference_ms = median([lap.lap_time_ms for lap in pools[reference]])
    return {
        code: {
            "deltaS": (0.0 if code == reference else
                       (median([lap.lap_time_ms for lap in matched])
                        - reference_ms) / 1000.0),
            "basis": (
                f"{len(matched)} laps against {reference} in one session, "
                f"all within {PACE_MAX_TYRE_AGE} laps of a set going on "
                f"and inside a {PACE_FUEL_BAND_L:.0f} L fuel band"),
        }
        for code, matched in pools.items()
    }


# Said beside every refusal, in one wording: the practice report compares a
# wider unit, and its figure - where it has one - is not this one.
PRACTICE_PANEL_NOTE = (
    "(The Practice screen's By tyre panel may show a gap across back-to-back "
    "sessions; that weaker figure carries whatever changed between the "
    "sessions and is not used here.)")


def comparable_pace_gap(laps: list[LapInput], reference: str | None,
                        code: str) -> str:
    """Why this compound has no pace figure, and what would produce one."""
    candidates = _pace_candidates(laps)
    matched = len(candidates.get(code, []))
    fix = ("The run that fixes it: back-to-back short runs, one per compound, "
           "in one session, each from the same fuel load.")

    if not reference or code == reference:
        return (f"{code} is the reference compound, but no other compound "
                f"shares a session with it on comparable laps, so there is "
                f"nothing to be a reference for. {fix} {PRACTICE_PANEL_NOTE}")

    together = ({lap.session_id for lap in candidates.get(code, [])}
                & {lap.session_id for lap in candidates.get(reference, [])})
    if not together:
        shared = f"no session in common with {reference}"
    else:
        shared = (f"{len(together)} session"
                  f"{'' if len(together) == 1 else 's'} in common with "
                  f"{reference}, and too few comparable laps in "
                  f"{'it' if len(together) == 1 else 'them'}")

    return (
        f"No like-for-like pace for {code}: {matched} lap"
        f"{'' if matched == 1 else 's'} inside {PACE_MAX_TYRE_AGE} laps of a "
        f"fresh set, and {shared}. Any figure would compare the sessions "
        f"rather than the compounds - whole-session medians made a Racing "
        f"Medium read quicker than a Racing Soft. {fix} {PRACTICE_PANEL_NOTE}")


def _daylight_value(daylight: dict) -> str:
    span = daylight.get("raceSpanH")
    if not span:
        return "not declared"
    hours = daylight.get("uncoveredHours") or []
    covered = "all driven" if not hours else f"{len(hours)} h never driven"
    length = daylight.get("raceSpanHours") or 0.0
    # A 24-hour race starts and finishes on the same clock reading, so the
    # span alone would say "18:00-18:00" and read as no race at all.
    through = f" ({length:.0f} h of game time)" if length >= 2.0 else ""
    return f"{_clock(span[0])}-{_clock(span[1])}{through}, {covered}"


def _clock(hour: float) -> str:
    whole = int(hour % 24.0)
    return f"{whole:02d}:{int(round((hour % 24.0 - whole) * 60)) % 60:02d}"


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


def _current_sheet_id(store, event) -> int | None:
    """Always None: the app no longer records which setup is in the car.

    This used to name the sheet fitted now, so that a lap run on a superseded
    one could be weighed down - it is describing a car that no longer exists.
    With the setup record gone there is nothing to be superseded BY, and
    everything weighs on age alone, which the recency model already documents
    as the right answer in that case.

    **Kept as a seam rather than deleted.** `recency.weight_of` still honours
    a sheet id, and the stored laps of 96 sessions still carry theirs, so the
    demotion is not dead code - it is a question this app can no longer ask.
    Returning a stale id would be worse than returning none: the last sheet
    ever written would silently become "the current car" forever, and every
    lap driven since would be weighed against a setup nobody is running.
    """
    return None


def _achieved_lap_ms(counted) -> int | None:
    """The median lap AS DRIVEN - incidents included, struck laps excluded.

    None where there is nothing to take a median of. Used only to estimate how
    many laps fit in a clock; never to cost a plan, where the clean pace is
    the right figure and this one would flatter the stop count.
    """
    times = sorted(lap.lap_time_ms for lap in counted if lap.lap_time_ms > 0)
    if not times:
        return None
    return times[len(times) // 2]


def build_inputs(store, event_id: int, *,
                 remember: bool = True) -> tuple[RaceInputs, list[Evidence]]:
    """Assemble the model's inputs from the event and its practice laps."""
    event = store.get_event(event_id)
    if event is None:
        raise ValueError(f"no event with id {event_id}")

    laps = _lap_inputs(store, event_id)

    # **A physics update is not an age.** `analysis/recency` weights old laps
    # down because the driver got faster and the setup moved on; that is a
    # decay and a weight expresses it. A patch is a discontinuity: laps either
    # side of GT7 1.71 are not weaker and stronger evidence about one car, they
    # are evidence about two. So the current version's laps are used alone
    # where there are enough of them, everything older is held back rather
    # than blended in, and where there is not enough the plan says out loud
    # that it rests on pre-patch evidence.
    selection = prefer_current(laps, _planning_version(store, event),
                               minimum=MIN_LAPS_ON_VERSION)
    laps = selection.laps

    counted = counted_laps(laps)

    # **Later laps count for more**, because he is getting faster and the
    # car keeps changing. Across the Monza set the pooled median is
    # 109.43 s and the latest session alone is 109.06 - 0.37 s a lap, or
    # about ten seconds over a 50-minute race, and because a stint ends
    # where degradation crosses a threshold it moves the stop lap too.
    #
    # Pace and fuel only. The wear rate is read off the in-game gauge
    # rather than fitted to lap times, so down-weighting old readings
    # would be reweighting a measurement - and a gauge reading from three
    # weeks ago is exactly as true as one from today.
    current_sheet = _current_sheet_id(store, event)
    fuel_per_lap, weighting = weighted(
        counted,
        lambda lap: (lap.fuel_start - lap.fuel_end
                     if lap.fuel_start > lap.fuel_end else None),
        current_sheet_id=current_sheet)
    fuel_per_lap = round(fuel_per_lap, 3) if fuel_per_lap is not None else None
    # **And re-costed for the fuel map the race will actually be run on.**
    # The map is declared on the event page and there is no other way it can
    # reach the app - GT7 broadcasts no such channel. Until 20 Sep 2026
    # nothing consumed the declaration at all: `FUEL_MAP_CONSUMPTION` was
    # referenced by tests only, and a plan costed on map-1 practice laps for a
    # race run on map 3 was 22% out on the one number that decides the stop
    # count (Bathurst Rd 8 - 10.625 planned, 8.2-8.5 raced; at the table's
    # x0.85 the answer would have been two stops rather than three).
    #
    # `burn_at_fuel_map` refuses far more often than it converts, and that is
    # the point: `laps.fuel_map` has been NULL on every lap since session 83,
    # so the usual answer is the burn unchanged with a sentence saying it
    # could NOT be re-costed. An unrecorded practice map is not map 1 (rule 3).
    raced_map = _event_int(event, "fuel_map")
    evidence_map = _evidence_fuel_map(counted)
    as_measured = fuel_per_lap
    fuel_per_lap, fuel_map_note = burn_at_fuel_map(
        fuel_per_lap, measured_on=evidence_map, racing_on=raced_map)
    # **And the scatter moves with the rate, because it is the same laps.**
    # `fuel_sd_l` sizes every fill margin (`fuel_margin_l` multiplies it by
    # the rate), so a converted mean beside an unconverted spread is two
    # quantities measured on two different maps. Scaling the mean without the
    # spread under-states the margin on a richer map, which is the direction
    # that runs him dry. Applied below, where the spread is computed.
    map_ratio = (fuel_per_lap / as_measured
                 if as_measured and fuel_per_lap else 1.0)
    # **The spread on that burn, and it is what decides how much fuel goes in
    # at the stop.** Unweighted and unrounded: the weighting exists to pick a
    # central value across sessions of different ages, and applying it to a
    # dispersion would report a spread narrower than the laps actually show.
    # Every lap that produced a burn counts, because a margin sized on a
    # flattered spread is a margin that runs the car dry.
    by_session: dict[object, list[float]] = {}
    burns: list[float] = []
    loads: list[float] = []
    for lap in counted:
        if lap.fuel_start <= lap.fuel_end:
            continue
        used = lap.fuel_start - lap.fuel_end
        burns.append(used)
        # **The load that burn was measured at.** Burn rises with what is in
        # the tank (+0.0061 L per litre aboard, measured), so `fuel_per_lap_l`
        # is only meaningful beside the load its own laps were carrying -
        # correcting it to another load without an origin double-counts. The
        # mid-lap value is the lap's mean load. See `strategy/fuel_model.py`.
        loads.append((lap.fuel_start + lap.fuel_end) / 2.0)
        by_session.setdefault(getattr(lap, "session_id", None), []).append(used)
    fuel_sd = consecutive_sd(by_session.values())
    if fuel_sd is not None and map_ratio != 1.0:
        fuel_sd = fuel_sd * map_ratio
    # None rather than 0.0 where nothing was measured: zero is a real fuel
    # load and would tell the model the burn was taken on an empty tank.
    fuel_reference_load = (sum(loads) / len(loads)) if loads else None
    # **Two disciplines look like one number unless somebody checks.** On
    # session 60 ten laps were deliberately short-shifted and two run at full
    # RPM: 5.15-5.36 L against 6.66-6.81 L, a clean 27% step. `short_shift_rpm`
    # reads 0.0 on all twelve, so nothing downstream can separate them and the
    # weighted median lands on the short-shifted figure. A plan costed on it
    # goes into a full-RPM race a quarter light on fuel.
    fuel_split = find_split(burns)
    # The same estimator on lap time, and only a timed race reads it: it is
    # what decides whether the clock's own lap count is resolvable enough to
    # fuel exactly to. See `RaceInputs.lap_count_firm`.
    laps_by_session: dict[object, list[float]] = {}
    for lap in counted:
        if lap.lap_time_ms:
            laps_by_session.setdefault(
                getattr(lap, "session_id", None), []).append(
                    lap.lap_time_ms / 1000.0)
    lap_time_sd = consecutive_sd(laps_by_session.values())
    # **The pace reference, not the degradation reference.** This called
    # `green_lap_reference_ms` - the best of the oldest session's opening
    # laps, kept fresh-tyre-early on purpose for the wear fit - against that
    # function's own docstring, which says in as many words to use
    # `reference_pace_ms` for the pace a plan is built on. The wrong number
    # twice over set the stop laps, the timed race's distance, and the live
    # pace-drift comparison: one race was judged "2% slower than planned"
    # against a three-day-old opening lap its own laps 2-3 promptly beat.
    # The green-lap figure still does its real job in `analysis/wear`.
    reference_ms, _ = reference_pace_ms(laps, current_sheet_id=current_sheet)
    wear = wear_rate(laps)
    capacity = _fuel_capacity(store, event_id)

    # The compound the evidence came from. Stints default to it, because a
    # wear rate measured on one compound does not describe another.
    evidence_compound = reference_compound(counted)
    profiles = compound_profiles(laps, evidence_compound)

    # For a timed race the stored figure is minutes, not laps. The lap count
    # is only a starting estimate: what the race actually covers depends on
    # how many times the car stops, and the model works that out per plan.
    # Measured off the fuel channel where a stop was ever recorded; the typed
    # figure otherwise, labelled as typed. At 100 L it is most of a pit stop.
    refuel = refuel_evidence(laps, event["refuel_rate_lps"])

    # What the race's conditions are, and whether anything has been driven in
    # them. GT7 gives no track temperature, so this is the only way to know.
    #
    # The lobby's time-of-day setting is a name, not an hour, and what it means
    # differs by circuit. So it is measured off the game clock rather than
    # looked up, kept against the circuit, and reused - and the circuit's own
    # clock ceiling caps the span, because a race cannot run into conditions
    # the track's clock will not reach.
    preset = event["time_of_day"] or ""
    reading = read_clock(laps)
    circuit = circuit_key(event["track"], event["layout"])
    # **`remember=False` makes this a reader** (row 2.10 pass 5). Reading the
    # evidence saved a row, so two doors documented as read-only - the MCP
    # `strategy_evidence` and `tools/shift_target.py` - wrote to the database
    # every time they were asked a question. The app's own paths still
    # remember the clock: it is measured off the game clock rather than looked
    # up, and it has to be kept somewhere to be reused.
    if reading.measured and remember:
        store.save_track_clock(circuit, preset, reading)
    known = store.get_track_clock(circuit, preset)
    minutes = (float(event["race_laps"] or 0)
               if event["race_type"] == "time" else None)
    span = race_span(
        reading if reading.measured else _reading_from(known), minutes,
        declared_start=_event_float(event, "start_hour"),
        declared_multiplier=_event_float(event, "time_multiplier"))
    daylight = coverage(laps, span)
    daylight["preset"] = preset
    daylight["clock"] = reading.as_export() if reading.measured else None
    daylight["sessionsToRun"] = sessions_to_run(daylight, preset=preset)
    # Practice run with the clock stopped keeps the lobby light and produces
    # plenty of laps in conditions the race will not have.
    #
    # **Against the race's declared multiplier, not practice's own.** This
    # passed the pooled practice reading whenever practice had one, so the
    # comparison was practice against itself: every session matched, nothing
    # was ever reported, and the one case the check exists for - practice run
    # with the clock frozen for a race that sweeps through the evening - was
    # the case it could not see. With no declared multiplier there is nothing
    # to compare against and the warning is withheld rather than invented.
    daylight["practiceClock"] = practice_clock_warning(
        [read_clock(list(run.laps)) for run in split_runs(laps)],
        _event_float(event, "time_multiplier"))

    # Can it rain here at all? Declared, never measured - GT7 broadcasts no
    # weather channel in any packet format.
    weather = wet_evidence(
        event["weather_rule"] if "weather_rule" in event.keys() else None,
        _rain_possible(event),
        sum(1 for lap in laps if is_wet_compound(lap.compound)),
        track=event["track"], layout=event["layout"])

    timed = event["race_type"] == "time"
    race_minutes = float(event["race_laps"] or 0) if timed else None
    race_laps = event["race_laps"] or 0
    timed_stops, timed_stop_s = 0, 0.0
    if timed:
        # **How many laps fit in the clock is a different question from how
        # fast the car goes, and it wants a different median.**
        #
        # `reference_ms` is the recency-weighted pace a plan is COSTED on and
        # it is right for that. It is wrong here: it describes clean laps, and
        # an incident lap does not make the car slower but it does consume the
        # clock. Measured on the 30-minute race, the clean median predicted
        # sixteen laps and the achieved median predicted fifteen, which is
        # what happened - so the plan he approved was one lap long, and every
        # stint length in it was cut to fit a race that never existed.
        #
        # The in-race estimate already uses the achieved figure
        # (`ExpectationTracker.achieved_lap_time_ms`). This is the same choice
        # made before the race, off practice: counted laps as they were
        # actually driven, struck laps out, incidents IN. It is a proxy - a
        # practice incident is not a race incident - and it remains a
        # starting estimate that `clock_bound_stints` re-derives per plan.
        achieved = _achieved_lap_ms(counted) or reference_ms
        if achieved:
            # **Less the stops.** First the count without them, then the
            # stops that count forces and what each costs, then the count
            # again with that time off the clock - see `laps_from_minutes`.
            naive = laps_from_minutes(race_minutes or 0, achieved)
            timed_stops, timed_stop_s = timed_race_stop_s(
                laps=naive, fuel_per_lap_l=fuel_per_lap, capacity_l=capacity,
                refuel_rate_lps=refuel["rateLps"] or event["refuel_rate_lps"],
                pit_loss_s=event["pit_loss_secs"],
                dead_time_s=PIT_DEAD_TIME_S,
                mandatory_stops=event["mandatory_stops"] or 0)
            race_laps = laps_from_minutes(race_minutes or 0, achieved,
                                          stops=timed_stops,
                                          stop_s=timed_stop_s)

    inputs = RaceInputs(
        weighting=weighting,
        race_laps=race_laps,
        race_minutes=race_minutes,
        start_hour=_event_float(event, "start_hour"),
        time_multiplier=_event_float(event, "time_multiplier"),
        extra_time_s=_extra_time_s(event),
        lap_time_ms=reference_ms or 0,
        fuel_per_lap_l=fuel_per_lap,
        fuel_sd_l=fuel_sd,
        fuel_samples=len(burns),
        fuel_reference_load_l=fuel_reference_load,
        fuel_map=raced_map,
        evidence_fuel_map=evidence_map,
        fuel_map_note=fuel_map_note,
        lap_time_sd_s=lap_time_sd,
        fuel_capacity_l=capacity,
        refuel_rate_lps=refuel["rateLps"] or event["refuel_rate_lps"],
        pit_loss_s=event["pit_loss_secs"],
        # Typed on the event page, so the payload says so. The evidence row
        # below has always called it declared; the export used to assert it
        # was measured at this track.
        pit_loss_source=PIT_LOSS_DECLARED,
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
                  else f"{race_minutes:g} min, about {race_laps} laps"
                       + (f" with {timed_stops} stop"
                          f"{'' if timed_stops == 1 else 's'} of ~"
                          f"{timed_stop_s:.0f} s off the clock"
                          if timed_stops else "")),
                 DECLARED if not timed else ASSUMED,
                 "" if not timed else _timed_race_note(inputs)),
        Evidence("Reference lap",
                 _lap_time(reference_ms), MEASURED if reference_ms else MISSING,
                 # Weighted like the fuel figure and for the same reason: the
                 # old note claimed "fastest of the first counted laps",
                 # which is the degradation reference's shape, not this one's.
                 f"recency-weighted pace over {len(counted)} counted laps"
                 if reference_ms else "run a practice lap"),
        Evidence("Fuel per lap",
                 f"{fuel_per_lap:.2f} L" if fuel_per_lap else "—",
                 # **A re-costed burn is derived, not measured** (rule 5).
                 # `burn_at_fuel_map` only converts where both the race's map
                 # and the evidence laps' map are known and differ, and the
                 # result rests on a published step table this app has never
                 # measured - so it may not wear the same badge as a figure
                 # taken straight off the stream.
                 (ASSUMED if (fuel_per_lap and raced_map is not None
                              and evidence_map is not None
                              and raced_map != evidence_map)
                  else MEASURED if fuel_per_lap else MISSING),
                 # Says it is weighted, because it is: an unqualified
                 # "median of 40 laps" would read as a plain median and the
                 # two are different numbers.
                 (f"weighted median of {weighting.sessions} "
                  f"{'session' if weighting.sessions == 1 else 'sessions'}, "
                  f"half-life {weighting.half_life_sessions:g}"
                  # **And the load it was measured at, because a burn without
                  # one is not comparable to the session being planned.**
                  # Practice runs whatever fuel happened to be in the car; a
                  # race starts on a full tank and a qualifying run starts
                  # near-empty, and burn moves +0.0061 L per litre aboard. A
                  # median taken light under-fuels a race; taken heavy it
                  # over-fuels a flyer. See `strategy/fuel_model.py`.
                  + (f", measured at a mean {fuel_reference_load:.0f} L aboard"
                     if fuel_reference_load is not None else
                     ", and no lap reported a tank level, so it cannot be "
                     "corrected for fuel load")
                  # **And which fuel map, because a burn is per map.** The
                  # note is present whenever a map was declared, including
                  # when it could NOT be used - an absent sentence would read
                  # as "the question does not arise", which is how a map-1
                  # burn came to be spent on a map-3 race.
                  + (f". Fuel map: {fuel_map_note}" if fuel_map_note else "")
                  if fuel_per_lap else "no fuel burn recorded")),
        Evidence("Fuel map",
                 str(raced_map) if raced_map is not None else "—",
                 DECLARED if raced_map is not None else MISSING,
                 (fuel_map_note or "")
                 if raced_map is not None else
                 "no channel carries it - declare it on the event page, or "
                 "the plan is costed on whatever map practice happened to "
                 "run"),
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
        Evidence("Weather",
                 _weather_value(weather),
                 DECLARED if weather["canRain"] is not None else MISSING,
                 weather["note"]),
        Evidence("Time of day",
                 _daylight_value(daylight),
                 MEASURED if daylight.get("covered") else MISSING,
                 " ".join(part for part in (
                     (daylight.get("clock") or {}).get("note"),
                     daylight.get("practiceClock"),
                     daylight["note"]) if part)),
        Evidence("Refuel rate",
                 (f"{refuel['rateLps']:.2f} L/s" if refuel["rateLps"]
                  else "not set"),
                 MEASURED if refuel["source"].startswith("measured") else DECLARED,
                 refuel.get("note", "")),
        Evidence("Fuel weight",
                 f"{FUEL_WEIGHT_S_PER_L_PER_LAP:.3f} s/L/lap", ASSUMED,
                 "derived, not measured - overwrite it if you measure it"),
    ]
    # **Said out loud, at the top of the list.** A plan quietly built on
    # pre-patch laps looks exactly like one built on current ones, and the
    # whole point of holding the old laps back is that somebody knows it
    # happened.
    # **Above the plan, because it invalidates the number the plan is costed
    # on.** Not a correction: the app cannot tell which population the race
    # will be run at, and choosing for him would be inventing the answer.
    if fuel_split is not None:
        evidence.insert(0, Evidence(
            "Fuel burn is split",
            f"{fuel_split.low:.3g} / {fuel_split.high:.3g} L per lap",
            ASSUMED,
            fuel_split.describe()))

    if selection.note:
        evidence.insert(0, Evidence(
            "Evidence version",
            selection.version or "mixed",
            ASSUMED if selection.stale else MEASURED,
            selection.note))

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
