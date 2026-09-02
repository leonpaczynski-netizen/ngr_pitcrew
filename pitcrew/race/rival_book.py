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

from pitcrew.race.profile import FULL_TANK_L, Observation, Profile, describe
from pitcrew.race.profile import field_stop_fraction

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
        reads=seen.reads, watched_s=seen.watched_s, partial=seen.partial)


def profile_of(store, driver: str, *,
               include_partial: bool = COUNT_PARTIAL_IN_RATES) -> Profile:
    """Everything on file about one driver, as a `Profile`."""
    profile = Profile(driver)
    for row in store.rival_stops(driver, include_partial=True):
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
                             else FULL_TANK_L)))
    return profile


def everyone(store) -> list[Profile]:
    """A profile per driver who has ever been seen stopping."""
    names = sorted({row["driver"] for row in store.rival_stops()})
    return [profile_of(store, name) for name in names]


def briefing(store, *, ours_burn_l: float | None = None,
             drivers: list[str] | None = None) -> list[str]:
    """What is known about the field, in plain sentences, before a race.

    The pre-race read: who uses more fuel than us, who carries what he does not
    need, who stops early. Empty where nobody has been watched, which is the
    honest answer for a first race at a new circuit and not a claim that the
    field has no habits.
    """
    profiles = everyone(store)
    if drivers is not None:
        wanted = set(drivers)
        profiles = [p for p in profiles if p.driver in wanted]
    if not profiles:
        return []
    middle = field_stop_fraction(profiles)
    lines: list[str] = []
    for profile in sorted(profiles, key=lambda p: -p.stops_seen):
        said = describe(profile, ours_burn_l=ours_burn_l,
                        field_fraction=middle)
        if said:
            lines.extend(said)
    return lines


def teammate_of(store) -> str | None:
    """The driver flagged as the teammate, if one has been."""
    return store.teammate_name()
