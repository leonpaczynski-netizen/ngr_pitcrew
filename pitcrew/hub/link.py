"""Tying a Pit Crew race to the league it belongs to, and keeping the title live.

`read.py` opens the hub and `standings.py` does the arithmetic. This is what
connects them to a race that is actually running: which league this is, who the
team mate is in it, what has to be finished, and how that changes as the race
moves.

### Matching a race to a league

Three ways, in order of how much they can be trusted:

1. **The event says so.** `events.series` holds a league name; if it matches one
   on the hub, that is the answer and nothing else is guessed at.
2. **The car says so.** He runs a different car in each league - a Huracan in
   GR3, a Shelby in Supercars, a 911 RSR in the Porsche Cup - so the car is
   very nearly a key on its own.
3. **Nothing says so.** Then there is no league, and every championship answer
   is `None`. A race matched to the wrong league would compute a title from
   somebody else's points, which is worse than computing none.

### Live standings mean projecting THIS race onto the table

The championship does not move until a result is filed, so "live standings" is
the table plus this race as it currently stands: our position from telemetry,
and the rivals' from the leaderboard. **It is a projection and is labelled
one.** The board shows the top eight only, so a title rival outside it is
projected on his current points alone - which understates him, and that is the
safe direction: it never invents a threat, it can only miss one, and the ones
it can miss are by definition not in the places that score.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.hub.read import Hub
from pitcrew.hub.standings import (
    Standing,
    TitleMath,
    points_for_position,
    resolve_scheme,
    standings,
    title_math,
)


def _same_car(theirs: str | None, ours: str) -> bool:
    """Whether two car names from two applications are the same car.

    They agree exactly on this driver's archive - both store
    "Lamborghini Huracan GT3 '15" - but they are two apps maintained apart, so
    the comparison is normalised rather than trusting that to hold. Case,
    surrounding space and punctuation are dropped; the accented letter is NOT,
    because dropping it would make two different cars compare equal more often
    than it would rescue a mismatch.
    """
    if not theirs or not ours:
        return False
    def flat(text: str) -> str:
        return "".join(ch for ch in text.casefold() if ch.isalnum())
    return flat(theirs) == flat(ours)


@dataclass
class LeagueRace:
    """One race, seen as a round of a championship.

    Everything is `None` or empty where the hub could not answer, and the whole
    object is optional: the app raced for months without it and must go on
    doing so when the hub is not there.
    """
    series_id: str | None = None
    series_name: str | None = None
    matched_by: str = "nothing"
    teammates: list[str] = field(default_factory=list)
    table: list[Standing] = field(default_factory=list)
    rounds_left: int = 0
    scheme: tuple = ()
    pole_points: int = 0
    fastest_lap_points: int = 0
    field_size: int | None = None
    taken_at: str = ""
    stale: bool = False

    @property
    def known(self) -> bool:
        return bool(self.series_id and self.table)


def league_for(hub: Hub, event: dict, me: str) -> LeagueRace:
    """Work out which championship this race belongs to.

    `me` is the driver's own name as the hub spells it. Returns an empty
    `LeagueRace` rather than a guess when nothing matches.
    """
    out = LeagueRace(taken_at=hub.freshness(), stale=hub.stale)
    if not hub.available:
        return out
    driver = hub.driver_by_name(me)
    if driver is None:
        return out
    mine = [s for s in hub.my_series(driver.id) if s.status == "ACTIVE"]
    if not mine:
        return out

    wanted = (event.get("series") or "").strip().lower()
    found, how = None, "nothing"
    if wanted:
        found = next((s for s in mine if s.name.lower() == wanted), None)
        how = "the event names it" if found else how
    if found is None:
        car = (event.get("car_name") or "").strip().lower()
        if car:
            # The car is nearly a key: a different one in each league.
            hits = []
            for series in mine:
                for entry in hub.entries(series.id):
                    if (entry.driver_id == driver.id
                            and _same_car(entry.car_name, car)):
                        hits.append(series)
                        break
            # **Only when it is unambiguous.** Two leagues in one car is not a
            # match, it is a coin toss, and a title computed from the wrong
            # league is worse than none.
            if len(hits) == 1:
                found, how = hits[0], "the car"
    if found is None:
        return out

    results = hub.results(found.id)
    rounds = hub.rounds(found.id)
    done = {row["roundId"] for row in results}
    out.series_id = found.id
    out.series_name = found.name
    out.matched_by = how
    out.teammates = hub.teammates(found.id, driver.id)
    out.scheme = found.points_scheme
    out.pole_points = found.pole_points
    out.fastest_lap_points = found.fastest_lap_points
    out.rounds_left = len([r for r in rounds if r["id"] not in done])
    out.field_size = len(hub.entries(found.id)) or None
    out.table = standings(results, scheme=found.points_scheme,
                          pole_points=found.pole_points,
                          fastest_lap_points=found.fastest_lap_points)
    return out


def before_the_start(race: LeagueRace, me: str,
                     on_the_grid=None) -> TitleMath | None:
    """The championship as it stands on the grid, before a wheel turns."""
    if not race.known:
        return None
    math = title_math(race.table, ours=me, rounds_left=race.rounds_left,
                      scheme=race.scheme, pole_points=race.pole_points,
                      fastest_lap_points=race.fastest_lap_points,
                      field_size=race.field_size)
    if on_the_grid:
        math.live_rivals = math.matters_here(on_the_grid) or math.live_rivals
    return math


def project(race: LeagueRace, me: str, our_position: int | None,
            rival_positions: dict | None = None) -> list[Standing]:
    """The table as it would stand if the race finished right now.

    A PROJECTION and never presented as the standings. Drivers not on the
    leaderboard keep their current points - the board shows eight, so a rival
    further back is projected on what he already has. That understates him,
    which is the safe direction: it can miss a threat but never invent one, and
    the ones it misses are outside the scoring places anyway.
    """
    if not race.known:
        return []
    scheme = resolve_scheme(race.scheme)
    finishing = dict(rival_positions or {})
    if our_position is not None:
        finishing[me] = our_position
    projected = []
    for standing in race.table:
        gained = points_for_position(finishing.get(standing.driver), scheme)
        projected.append(Standing(driver=standing.driver,
                                  points=standing.points + gained,
                                  races=standing.races + (
                                      1 if standing.driver in finishing else 0),
                                  best_finish=standing.best_finish))
    projected.sort(key=lambda s: (-s.points, s.best_finish or 99))
    return projected


def where_we_would_be(race: LeagueRace, me: str, our_position: int | None,
                      rival_positions: dict | None = None) -> int | None:
    """Our championship position if the race ended now, or `None`."""
    projected = project(race, me, our_position, rival_positions)
    for index, standing in enumerate(projected, start=1):
        if standing.driver == me:
            return index
    return None
