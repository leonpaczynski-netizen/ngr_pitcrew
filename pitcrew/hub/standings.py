"""Championship points, and what position secures the title.

### The arithmetic is mirrored from the hub, not invented

Every rule below is transcribed from the hub's own `src/lib/points.ts`, which
its docstring calls authoritative, and the transcription is deliberate: two
places computing a championship differently is worse than one place computing
it at all, and the driver would have no way to tell which was right.

    POINTS_TABLE   22 18 15 13 12 11 10 9 8 7 6 5 4 3 2 1, and 0 from P17
    DNS, DSQ       always 0, position ignored
    FINISHED, DNF  score identically from position; DNF is placed after the
                   classified finishers by the admin
    POSITION_DROP  applied at READ time - the stored position is always the
                   physical finishing order and is never mutated
    POINTS_DEDUCTION subtracted after, floored at 0
    multi-race     the finishing scheme is divided per race and rounded
                   INDEPENDENTLY per entry, so a round total may drift (22
                   becomes 7+7+7=21 over three races). Bonuses do NOT divide.

**Where a league has its own scheme on the hub, that is used instead**, exactly
as `resolveScheme` does there. The mirrored table is the default only, so the
day one is configured on the hub Pit Crew follows it without being changed -
which keeps the copied constant to the smallest surface it can have.

### What it is for

Not a league table for its own sake. It answers the question a driver asks on
the grid and again at half distance: **what do I have to finish to secure
this, and who in this race can still take it from me.**
"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field

# Transcribed from `src/lib/points.ts`. Positions 1-16 score; P17 and beyond
# score nothing.
POINTS_TABLE = (22, 18, 15, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1)

# Statuses that score nothing whatever the position says.
NO_SCORE = ("DNS", "DSQ")

POSITION_DROP, POINTS_DEDUCTION = "POSITION_DROP", "POINTS_DEDUCTION"


def resolve_scheme(scheme) -> tuple[int, ...]:
    """The league's own table where it has one, the default where it does not.

    The single place a default is chosen, mirroring the hub's `resolveScheme`
    for the same reason its docstring gives: every other helper delegates here
    rather than deciding for itself.
    """
    return tuple(scheme) if scheme else POINTS_TABLE


def normalise_for_races(scheme, race_count: int):
    """A multi-race round divides the finishing scheme and rounds per entry.

    Rounding is independent per entry, so the round total drifts - 22 becomes
    7+7+7 over three races. That drift is the hub's accepted behaviour and is
    reproduced rather than corrected, because a championship that disagrees
    with the league's own table is not a championship.

    **Absence is preserved.** An empty scheme stays empty: for the overall
    table that means "use the default", and for a class table it means "award
    no class points at all", and resolving one here would award class points to
    a league that had configured none.
    """
    if race_count <= 1 or not scheme:
        return scheme
    # **Half away from zero, like JavaScript's `Math.round`, not Python's
    # banker's rounding.** They disagree on four of sixteen positions at a
    # two-race round - Python gives P4 six where the hub gives seven, and P16
    # nothing where the hub gives one.
    return tuple(math.floor(value / race_count + 0.5) for value in scheme)


def effective_position(status: str | None, position: int | None,
                       penalties) -> int | None:
    """The finishing position after penalties, or `None` if unclassified.

    A read-time derivation. The stored position is the physical finishing
    order and is never changed - a place drop moves a driver down here and
    nowhere else.
    """
    if status in NO_SCORE or position is None:
        return None
    drop = sum(value for kind, value in (penalties or [])
               if kind == POSITION_DROP)
    return position + drop


def points_for_position(position: int | None, scheme=None) -> int:
    table = resolve_scheme(scheme)
    if position is None or not isinstance(position, int):
        return 0
    if position < 1 or position > len(table):
        return 0
    return table[position - 1]


def points_for_result(status: str | None, position: int | None,
                      penalties=None, scheme=None) -> int:
    """Points for one classified result, penalties folded in.

    Deductions come off the base and the total floors at zero: a penalty
    cannot put a driver into negative points.
    """
    where = effective_position(status, position, penalties)
    base = 0 if status in NO_SCORE else points_for_position(where, scheme)
    taken = sum(value for kind, value in (penalties or [])
                if kind == POINTS_DEDUCTION)
    return max(0, base - taken)


@dataclass
class Standing:
    """One driver's championship position and what it rests on."""
    driver: str
    points: int = 0
    races: int = 0
    best_finish: int | None = None

    def note(self, points: int, position: int | None) -> None:
        self.points += points
        self.races += 1
        if position is not None and (self.best_finish is None
                                     or position < self.best_finish):
            self.best_finish = position


def took_pole(row) -> bool:
    """Whether this result was pole, DERIVED as the hub derives it.

    **The stored `pole` boolean is legacy and is `0` on every row.** Measured
    on the live hub: 0 of 202 results carry the flag, while 189 carry a
    `qualifyingPosition` and 20 of those are P1. The hub therefore computes
    pole at every call site as `qualifyingPosition == 1` where that is present
    and falls back to the flag otherwise, and reading the flag alone made pole
    points dead - which inverted third and fourth in the GR3 championship.
    """
    where = row.get("qualifyingPosition")
    if where is not None:
        return int(where) == 1
    return bool(row.get("pole"))


def standings(results, *, scheme=None, pole_points: int = 0,
              fastest_lap_points: int = 0,
              races_per_round: int = 1,
              carry_in=None, precomputed=None,
              hidden=None) -> list[Standing]:
    """The championship table, highest first.

    `results` is `hub.read.Hub.results()`. Bonuses for pole and fastest lap are
    added at FULL value every race and are deliberately not divided by the race
    count - the hub does the same, and its comment says so.

    **`precomputed` wins outright where it exists.** `points.ts` says a
    persisted `MultiClassResultBreakdown` total is what every aggregation
    surface should prefer verbatim rather than re-deriving from position and
    class - and for the Enduro it is the only correct answer, because a
    multi-class result is an overall finish score PLUS a class score and no
    single finishing table can express that. Scoring it outright instead was
    measured 15-30% light on every driver AND in a different order: Farter999
    is sixth in the league on 43 and would have been read as 25.

    **`carry_in` is not optional in practice.** The Porsche Cup carries
    seventeen drivers' points forward, ninety-seven of them this driver's, and
    a table computed without them had him fourth on 31 where the league has him
    leading on 128.
    """
    table = normalise_for_races(resolve_scheme(scheme), races_per_round)
    # **Keyed on the normalised name, as the hub keys it.** `carry-in.ts`
    # matches on `trim().toLowerCase()`, so a carry-in written "beeni" against
    # results recorded as "Beeni" is ONE driver there and would have been two
    # here - each holding half a championship, with nothing on screen saying
    # the total had been split.
    # Banned drivers are dropped before anything is counted, so they cannot
    # shift a position or appear as a rival. `hidden` is already normalised.
    barred = set(hidden or ())
    tally: dict[str, Standing] = {}
    for name, points in (carry_in or {}).items():
        if _merge_key(name) in barred:
            continue
        tally[_merge_key(name)] = Standing(driver=name, points=int(points))
    for row in results:
        name = row.get("driverName")
        if not name:
            continue
        key = _merge_key(name)
        if key in barred:
            continue
        if key in tally:
            # The result's spelling wins, exactly as it does in the hub: only
            # an unmatched carry-in entry keeps the name written on the blob.
            tally[key].driver = name
        status = row.get("status")
        ready = (precomputed or {}).get(row.get("id"))
        if ready is not None:
            # Verbatim, bonuses included - they are already inside the total,
            # and adding them again would pay pole twice.
            got = int(ready)
        else:
            got = points_for_result(status, row.get("position"),
                                    row.get("penalties"), table)
            # **A non-starter collects no bonus either.** The hub returns all
            # four components as zero for DNS and DSQ, bonuses included;
            # adding them unconditionally paid a disqualified pole-sitter
            # three points.
            if status not in NO_SCORE:
                if took_pole(row):
                    got += pole_points
                if row.get("fastestLap"):
                    got += fastest_lap_points
        tally.setdefault(key, Standing(driver=name)).note(
            got, effective_position(status, row.get("position"),
                                    row.get("penalties")))
    # **Ties break on the name, as the hub breaks them.** Ordering by best
    # finish instead put two level drivers in a different order from the
    # league's own site, and the championship position quoted to the driver
    # came from this sort.
    ranked = sorted(tally.values(),
                    key=lambda s: (-s.points, _name_key(s.driver)))
    return ranked


def _merge_key(name: str) -> str:
    """Two spellings of one driver, reduced to one key.

    `normalizeCarryInName` in the hub is `trim().toLowerCase()`; this must
    agree with it or the two applications disagree about how many drivers are
    in the championship.
    """
    return (name or "").strip().lower()


def _name_key(name: str) -> str:
    """A name compared as the hub compares it.

    `localeCompare(..., {sensitivity: "base"})` ignores case AND accent, so
    stripping the case alone would still order an accented name differently
    from the league's own site.
    """
    stripped = unicodedata.normalize("NFKD", name or "")
    return "".join(c for c in stripped
                   if not unicodedata.combining(c)).casefold()


@dataclass
class TitleMath:
    """What is still possible in the championship, and for whom.

    `secures` is the position that guarantees the title WHATEVER the rivals do
    - the pessimistic case, where every one of them wins everything left. It is
    the only figure worth saying to a driver, because a position that only
    works if somebody else has a bad day is not a plan.
    """
    leader: str | None = None
    ours: str | None = None
    # **`None` means we are not in this table, and `0` means we are and have
    # scored nothing.** Defaulted to `0`, a driver the lookup could not find
    # was indistinguishable from a pointless one, and every downstream test
    # read as if he were racing (rule 3).
    our_points: int | None = None
    # **Signed, and named for what it is.** Positive means we lead the
    # championship by this much; negative means we trail it. It was called
    # `lead_over_next` and went negative whenever we were not first, which is
    # a field whose name contradicts its value four times out of four on this
    # driver's own leagues.
    # **Two references, two names.** One signed field meant "gap to the
    # leader" when behind and "lead over the next man" when ahead - the same
    # word for figures that demand opposite driving, which is CLAUDE.md rule
    # 13. Measured against the leader alone it was identically zero every time
    # we led, and the driver heard "leading by 0".
    margin_to_leader: int = 0          # <= 0 always; 0 exactly when leading
    lead_over_next: int | None = None  # only when leading, else None
    rounds_left: int = 0
    most_still_available: int = 0
    secures_position: int | None = None
    already_secured: bool = False
    out_of_reach: bool = False
    live_rivals: list[str] = field(default_factory=list)
    # **Where the rival list was narrowed from, or "" for not narrowed at
    # all.** A list filtered against drivers actually seen on the board and a
    # list nobody has checked are different claims, and only one of them is
    # worth a name in the driver's ear (rule 5).
    rivals_from: str = ""

    @property
    def leading(self) -> bool:
        return self.ours is not None and self.ours == self.leader

    def to_say(self) -> str:
        """One sentence for the grid. Never a table.

        `secures_position` being `None` is the ordinary answer with rounds
        still to run and must not read as a missing value: with three rounds
        left and seventy-five points available, no single finish secures
        anything, and saying so is the honest call.
        """
        # **Not finding ourselves is silence, not victory.** The hub matches
        # a driver case-insensitively AND on his PSN name - "Beeni-187" for
        # "Beeni" - while the table was searched with a bare `==`. The lookup
        # missed, `live_rivals` came back empty because nothing had been
        # compared, and the third branch below announced the championship won
        # in a league where `already_secured` was False. An empty rival list
        # has two causes and only one of them is good news (rule 12).
        if self.our_points is None:
            return ""
        if self.already_secured:
            return "The championship is already yours."
        if self.out_of_reach:
            return "The championship is gone; this is for the placing."
        if not self.live_rivals:
            return "Nobody left can catch you."
        if self.secures_position:
            return (f"P{self.secures_position} today secures it, whatever "
                    f"they do.")
        where = ("leading by %d" % self.lead_over_next
                 if self.leading and self.lead_over_next is not None
                 else "leading" if self.leading
                 else "%d behind" % -self.margin_to_leader)
        return (f"Nothing settles it today - {where}, "
                f"{self.most_still_available} still on the table.")

    def matters_here(self, on_the_grid) -> list[str]:
        """The title rivals who are actually in THIS race.

        Everybody else on the board is a place, not a championship. Defending
        against a driver who cannot take the title costs the race being driven
        for one that is not in danger.
        """
        here = {_merge_key(str(name)) for name in (on_the_grid or ())}
        return [name for name in self.live_rivals
                if _merge_key(name) in here]


def title_math(table: list[Standing], *, ours: str,
               rounds_left: int, scheme=None,
               pole_points: int = 0, fastest_lap_points: int = 0,
               field_size: int | None = None,
               per_race_max: int | None = None) -> TitleMath:
    """What we must finish to secure it, and who can still take it.

    The rival set is the honest part. **Only a driver who could still pass us
    if he won everything left is a title rival**; everybody else is racing for
    a place, and telling the driver to defend against them costs him the race
    he is actually in.
    """
    points = resolve_scheme(scheme)
    # **The caller may know a bigger ceiling than the finishing table.**
    # A multi-class round pays an overall finish AND a class finish and
    # both class bonuses - 47 a round in the Enduro against the 22 this
    # computes - so "still on the table" was understated by more than
    # half. Understating it is the unsafe direction: it makes a title look
    # settled while it is not.
    if per_race_max is None:
        per_race_max = ((points[0] if points else 0) + pole_points
                        + fastest_lap_points)
    available = max(0, rounds_left) * per_race_max

    # Matched as the hub matches names everywhere else - case and accent
    # folded - because `read.driver_by_name` accepts either spelling and the
    # caller has no way to know which one came back.
    wanted = _merge_key(ours)
    mine = next((s for s in table if _merge_key(s.driver) == wanted), None)
    out = TitleMath(leader=table[0].driver if table else None,
                    ours=mine.driver if mine else ours,
                    our_points=mine.points if mine else None,
                    rounds_left=max(0, rounds_left),
                    most_still_available=available)
    if mine is None or not table:
        return out

    others = [s for s in table if s is not mine]
    out.margin_to_leader = mine.points - table[0].points
    if mine is table[0] and others:
        out.lead_over_next = mine.points - others[0].points
    # **Level is not beaten.** There is no countback anywhere in the league's
    # own code, so a rival who can finish exactly level is not a rival we have
    # beaten - and `>` declared the title won with one still able to draw.
    out.live_rivals = [s.driver for s in others
                       if s.points + available >= mine.points]

    if not out.live_rivals:
        out.already_secured = mine is table[0]
    # Could we still be caught even winning out?
    out.out_of_reach = bool(others) and (
        mine.points + available < others[0].points)

    if out.already_secured or out.out_of_reach or not out.live_rivals:
        return out

    # The pessimistic case: every live rival takes the maximum from here.
    worst_rival = max(s.points for s in others) + available
    need = worst_rival - mine.points
    if need < 0:
        out.already_secured = True
        return out
    # **The WORST finish that still does it, not the best.** Points fall as
    # the position rises, so the first position to satisfy the inequality is
    # always P1 - which is true and useless: "win it and you win it" is not a
    # call. What the driver needs is the lowest he can afford, so this keeps
    # the LAST position that still holds.
    limit = field_size or len(points)
    for position in range(1, limit + 1):
        gained = points_for_position(position, points)
        if mine.points + gained > worst_rival:
            out.secures_position = position
        else:
            break
    return out
