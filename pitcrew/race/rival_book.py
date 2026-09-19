"""The rival dataset: what every driver did, race after race.

`pit_wall.py` watches one race. This is the book it writes into and reads back
from, so that arriving at Spa in October the engineer already knows what Rocky
did at Spa in September.

### It is a book of observations, not of conclusions

Nothing is aggregated on the way in. Each stop is stored as it was seen -
litres in, litres out, how many readings stood behind them, whether the watcher
joined mid-fill - and every judgement is made on the way out, where the sample
count is still attached to it. That ordering is deliberate: a mean burn rate
written into a column is a number nobody can later discover was built on one
partial sighting.

### What pools across leagues and what does not

He races more than one series at a time. **Litres a lap is the CAR's number**,
so a burn rate is scoped to one car and never averaged across them - a Gr.3 and
a Gr.4 figure are different quantities and their mean describes neither race.
**When he stops and whether he carries spare fuel are the DRIVER's**, so those
pool across everything, which is also where the samples are: a stop is one
observation a race and three is the floor for calling anything a habit.

Identity pools too. The same people race under the same names in his leagues,
so one `drivers` row is one person and the name bitmap recognises him anywhere.
The team mate does NOT pool - that is a fact about a pairing, and it lives in
`series_teammates`.

### Two things bound what it can ever say

**The board is truncated to the top eight**, and a car drops places while it
stands in the pit lane, so a driver near the cut goes below it exactly when he
becomes worth reading. The book is therefore better evidence about the leaders
than the midfield, and an empty page means "never seen stopping", never "does
not stop".

**A partial sighting is a floor, not a figure.** If the watcher joined after
the fill began, the lowest reading is an upper bound on his entry fuel and the
litres taken come out too small. Those rows are kept, because a floor is worth
having, and excluded by default from anything that computes a rate.
"""
from __future__ import annotations

from pitcrew.race.profile import (
    FULL_TANK_L,
    Observation,
    Profile,
    describe,
    field_without,
)

# A stop the watcher joined mid-fill is kept, but it does not get to set a
# burn rate: its entry figure is an upper bound and nothing in the number says
# so. It is still evidence about WHEN he stopped, which is why it is not thrown
# away.
COUNT_PARTIAL_IN_RATES = False


def record(store, session_id, seen, *, laps_total=None,
           assumed_start_l: float = FULL_TANK_L) -> int | None:
    """File one `pit_wall.Seen` in the book. Returns the row id, or None.

    A stop with no name attached is not filed: the whole value of the book is
    that tonight's stop joins up with the same driver's last one, and a row
    keyed on an anonymous cluster id joins up with nothing - the ids are
    per-session.
    """
    if seen is None or not seen.driver:
        return None
    stop = seen.stop
    return store.record_rival_stop(
        session_id, seen.driver, lap=stop.lap, laps_total=laps_total,
        fuel_in_l=stop.fuel_in_l, fuel_out_l=stop.fuel_out_l,
        compound=stop.compound, assumed_start_l=assumed_start_l,
        reads=seen.reads, compound_reads=seen.compound_reads,
        watched_s=seen.watched_s, partial=seen.partial,
        compound_in=getattr(stop, "compound_in", None))


def _circuit_of(row) -> str | None:
    """The stop's circuit, in the store's own vocabulary.

    **`analysis.resolve.circuit_key`, not a key composed here.** The first
    version built `f"{track} {layout}"`, which is a fourth spelling of a
    thing this codebase already has one canonical spelling for - the same
    key `grip_observations`, `tyre_models` and `controller.circuit_key_for`
    are indexed on, and `store/db.py` says outright that no caller should
    compose its own. It was self-consistent, so it worked; it was also
    exactly the defect this change set out to remove, one layer down.

    Joined onto the stop rather than looked up later, so a burn always knows
    which lap it is litres of.
    """
    track = row.get("track") if hasattr(row, "get") else None
    if not track:
        return None
    from pitcrew.analysis.resolve import circuit_key

    return circuit_key(str(track),
                       row.get("layout") if hasattr(row, "get") else None)


def profile_of(store, driver: str, *,
               include_partial: bool = COUNT_PARTIAL_IN_RATES,
               series: str | None = None) -> Profile:
    """Everything on file about one driver, as a `Profile`.

    Every stop he has made, pooled - the scoping happens on the way OUT, where
    the figure being computed decides. Pass `series` only to answer a question
    that is genuinely about one league.
    """
    profile = Profile(driver)
    for row in store.rival_stops(driver, include_partial=True, series=series):
        if row["partial"] and not include_partial:
            continue
        if row["lap"] is None:
            continue
        profile.add(Observation(
            driver=driver,
            race=str(row["session_id"]) if row["session_id"] else "unknown",
            lap=int(row["lap"]),
            laps_total=row["laps_total"],
            fuel_in_l=row["fuel_in_l"],
            fuel_out_l=row["fuel_out_l"],
            compound=row["compound"],
            assumed_start_l=(row["assumed_start_l"]
                             if row["assumed_start_l"] is not None
                             else FULL_TANK_L),
            series=row.get("series"), car=row.get("car_name"),
            circuit=_circuit_of(row)))
    return profile


def everyone(store, *, series: str | None = None) -> list[Profile]:
    """A profile per driver who has ever been seen stopping.

    `series` narrows to the field of one league; without it this is everybody
    he has ever raced, which is the right answer for "who is this driver" and
    the wrong one for "who am I racing tonight".
    """
    names = sorted({row["driver"] for row in store.rival_stops(series=series)})
    return [profile_of(store, name) for name in names]


def briefing(store, *, ours_burn_l: float | None = None,
             drivers: list[str] | None = None,
             refuel_rate_lps: float | None = None,
             series: str | None = None, car: str | None = None,
             circuit: str | None = None) -> list[str]:
    """What is known about the field, in plain sentences, before a race.

    The pre-race read: who uses more fuel than us, who carries what he does not
    need, who stops early. Empty where nobody has been watched, which is the
    honest answer for a first race at a new circuit and not a claim that the
    field has no habits.
    """
    profiles = everyone(store, series=series)
    if drivers is not None:
        wanted = set(drivers)
        profiles = [p for p in profiles if p.driver in wanted]
    if not profiles:
        return []
    lines: list[str] = []
    for profile in sorted(profiles, key=lambda p: -p.stops_seen):
        # The field he is judged against excludes him.
        # **The circuit travels with the car**, so the briefing quotes the
        # figure the live race will quote. Unscoped here and scoped there,
        # the two held different numbers under one name (rule 13).
        said = describe(profile, ours_burn_l=ours_burn_l,
                        field_fraction=field_without(profiles, profile.driver),
                        refuel_rate_lps=refuel_rate_lps, car=car,
                        circuit=circuit)
        if said:
            lines.extend(said)
    return lines


def teammate_of(store, series: str | None = None) -> str | None:
    """The team mate for this series, if one has been named.

    Per series, because he races several leagues and the team mate differs in
    each. `None` for a league nobody has named one in, which is not the same
    as having no team mate.
    """
    return store.teammate_name(series)
