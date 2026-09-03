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
    _merge_key,
    _name_key,
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
    # Why there is no championship here, when there is a league but no table.
    refused: str = ""
    teammates: list[str] = field(default_factory=list)
    table: list[Standing] = field(default_factory=list)
    rounds_left: int = 0
    scheme: tuple = ()
    pole_points: int = 0
    fastest_lap_points: int = 0
    field_size: int | None = None
    # The driver's name as the HUB spells it. `driver_by_name` accepts his
    # PSN name too, so the string the caller passed in is not necessarily the
    # one the standings table is keyed on.
    our_name: str | None = None
    # Who has ENTERED the next round. A declaration, not the field - see
    # `Hub.signed_in`. Used only when nothing has actually been seen on the
    # board, which on the grid is always.
    entered: list = field(default_factory=list)
    # **The most one round can pay in THIS league.** For a multi-class round
    # that is an overall finish PLUS a class finish plus both class bonuses -
    # measured at 47 in the Enduro against the 22 an outright table assumes.
    # Everything downstream that asks "how much is still on the table" was
    # wrong by more than half.
    per_race_max: int = 0
    multi_class: bool = False
    carry_in: dict = field(default_factory=dict)
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

    # **A multi-class league is not scored outright.** The Enduro is
    # MULTI_CLASS_MANUFACTURER: a result is an overall finish score PLUS a
    # class one, which no single finishing table can express. Scoring it
    # outright was measured 15-30% light on every driver and in a different
    # order - Farter999 is sixth on 43 and read as 25 - so the hub's own
    # persisted totals are used instead, verbatim, as `points.ts` says every
    # aggregation surface should. Where they are absent the league is refused
    # rather than approximated.
    results = hub.results(found.id)
    ready: dict = {}
    if found.multi_class:
        try:
            ready = hub.precomputed_points(found.id)
        except Exception:
            ready = {}
        # **All of them or none.** A result the hub has not computed yet would
        # fall through to the outright table, putting two different scales in
        # one championship - a driver on 43 and a driver on 25 for the same
        # drive, with the total looking perfectly well-formed either way.
        missing = [r for r in results if r.get("id") not in ready]
        if missing:
            out.series_name = found.name
            out.matched_by = how
            out.refused = (
                f"{found.name} is scored per class and the hub copy has no "
                f"computed points for {len(missing)} of {len(results)} results")
            return out
    # A scheme that would not parse is not a scheme. CLAUDE.md rule 3: an
    # unreadable 44-point-a-win table must not quietly score 22.
    if found.points_scheme is None:
        out.series_name = found.name
        out.matched_by = how
        out.refused = f"{found.name}'s points scheme could not be read"
        return out

    rounds = hub.rounds(found.id)
    done = {row["roundId"] for row in results}
    try:
        barred = hub.hidden_drivers()
    except Exception:
        barred = set()
    try:
        out.entered = [n for n in hub.signed_in(found.id)
                       if n.strip().lower() not in barred]
    except Exception:
        out.entered = []
    out.our_name = driver.driver_name
    out.multi_class = found.multi_class
    head = resolve_scheme(found.points_scheme)
    if found.multi_class:
        # **The four components `sumBreakdown` adds, and no others.** A
        # multi-class result is an overall FINISH score plus a class finish and
        # the two CLASS bonuses; there is no overall-pole or overall-fastest-lap
        # column in the breakdown at all, and adding the outright bonuses on
        # top invents points the league does not pay.
        klass = resolve_scheme(found.class_points_scheme)
        out.per_race_max = ((head[0] if head else 0)
                            + (klass[0] if klass else 0)
                            + found.class_pole_points + found.class_fl_points)
    else:
        out.per_race_max = ((head[0] if head else 0)
                            + found.pole_points + found.fastest_lap_points)
    out.series_id = found.id
    out.series_name = found.name
    out.matched_by = how
    out.teammates = hub.teammates(found.id, driver.id)
    out.scheme = found.points_scheme
    out.pole_points = found.pole_points
    out.fastest_lap_points = found.fastest_lap_points
    out.rounds_left = len([r for r in rounds if r["id"] not in done])
    out.field_size = len(hub.entries(found.id)) or None
    out.carry_in = found.carry_in or {}
    out.table = standings(results, scheme=found.points_scheme,
                          pole_points=found.pole_points,
                          fastest_lap_points=found.fastest_lap_points,
                          races_per_round=found.race_count,
                          carry_in=found.carry_in, precomputed=ready,
                          hidden=barred)
    # **The hub's own age against this league's own rounds.** A flat day count
    # calls a two-day-old copy current; if a round ran last night the table is
    # describing a championship that has already moved.
    try:
        if hub.round_run_since(found.id, hub.taken_at):
            out.stale = True
    except Exception:
        pass
    return out


def before_the_start(race: LeagueRace, me: str,
                     on_the_grid=None) -> TitleMath | None:
    """The championship as it stands on the grid, before a wheel turns."""
    if not race.known:
        return None
    math = title_math(race.table, ours=race.our_name or me,
                      rounds_left=race.rounds_left,
                      scheme=race.scheme, pole_points=race.pole_points,
                      fastest_lap_points=race.fastest_lap_points,
                      field_size=race.field_size,
                      per_race_max=race.per_race_max or None)
    # **The board first, the entry list second, and no third option.** The
    # leaderboard reader needs twenty frames before it will name anybody, so
    # on the grid it knows nobody at all and the filter never ran - the driver
    # was told to watch the top three of a 26-name championship, none of whom
    # need be in tonight's race. The entry list is the hub's own sign-in sheet
    # for the next round: a declaration rather than an observation, but a
    # specific one.
    #
    # Once either source has something to say, an empty result stays empty.
    # `or` restored the full list whenever nobody present was a title rival -
    # which is exactly the case the filter exists for.
    if on_the_grid:
        math.live_rivals = math.matters_here(on_the_grid)
        math.rivals_from = "the board"
    elif race.entered:
        math.live_rivals = math.matters_here(race.entered)
        math.rivals_from = "the entry list"
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
    # **A multi-class result cannot be projected from the board.** It is an
    # overall finish score PLUS a class one, and the leaderboard gives overall
    # positions only - there is nothing on screen that says which class each
    # car is in, so the class half is unknowable live. Crediting the outright
    # half alone promoted this driver from fifth to third in the Enduro and
    # would have been spoken as "championship 3 if it ends here". No answer is
    # the correct answer here (rule 3).
    if race.multi_class:
        return []
    scheme = resolve_scheme(race.scheme)
    me = race.our_name or me
    # Keyed the way the table is keyed. The board's spelling and the hub's are
    # two vocabularies, and an exact match between them is a coincidence.
    finishing = {_merge_key(str(who)): where
                 for who, where in (rival_positions or {}).items()}
    if our_position is not None:
        finishing[_merge_key(me)] = our_position
    # **One driver per finishing position.** Our own place comes from
    # telemetry and the rivals' from the leaderboard - two sources with no
    # agreement between them - so two cars could both be given P1 and both
    # paid for winning. Where that happens nobody is paid for the disputed
    # place: an invented result is worse than a missing one.
    seen: dict[int, int] = {}
    for where in finishing.values():
        seen[where] = seen.get(where, 0) + 1
    finishing = {who: where for who, where in finishing.items()
                 if seen.get(where, 0) == 1}
    projected = []
    for standing in race.table:
        key = _merge_key(standing.driver)
        gained = points_for_position(finishing.get(key), scheme)
        projected.append(Standing(driver=standing.driver,
                                  points=standing.points + gained,
                                  races=standing.races + (
                                      1 if key in finishing else 0),
                                  best_finish=standing.best_finish))
    # **The same comparator the table itself uses.** Ordered by best finish
    # here and by name there, "P4 in the championship" on the grid and
    # "championship 4 if it ends here" mid-race were two different questions
    # answered by two different sorts - and under a helmet he cannot ask which
    # one he just heard (rule 13). `best_finish` was not even what its name
    # says: a DNF counts as a finish in it.
    projected.sort(key=lambda s: (-s.points, _name_key(s.driver)))
    return projected


def where_we_would_be(race: LeagueRace, me: str, our_position: int | None,
                      rival_positions: dict | None = None) -> int | None:
    """Our championship position if the race ended now, or `None`."""
    projected = project(race, me, our_position, rival_positions)
    wanted = _merge_key(race.our_name or me)
    for index, standing in enumerate(projected, start=1):
        if _merge_key(standing.driver) == wanted:
            return index
    return None
