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
    return tuple(round(value / race_count) for value in scheme)


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


def standings(results, *, scheme=None, pole_points: int = 0,
              fastest_lap_points: int = 0,
              races_per_round: int = 1) -> list[Standing]:
    """The championship table, highest first.

    `results` is `hub.read.Hub.results()`. Bonuses for pole and fastest lap are
    added at FULL value every race and are deliberately not divided by the race
    count - the hub does the same, and its comment says so.
    """
    table = normalise_for_races(resolve_scheme(scheme), races_per_round)
    tally: dict[str, Standing] = {}
    for row in results:
        name = row.get("driverName")
        if not name:
            continue
        got = points_for_result(row.get("status"), row.get("position"),
                                row.get("penalties"), table)
        if row.get("pole"):
            got += pole_points
        if row.get("fastestLap"):
            got += fastest_lap_points
        tally.setdefault(name, Standing(driver=name)).note(
            got, row.get("position"))
    ranked = sorted(tally.values(),
                    key=lambda s: (-s.points, s.best_finish or 99))
    return ranked


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
    our_points: int = 0
    # **Signed, and named for what it is.** Positive means we lead the
    # championship by this much; negative means we trail it. It was called
    # `lead_over_next` and went negative whenever we were not first, which is
    # a field whose name contradicts its value four times out of four on this
    # driver's own leagues.
    margin_to_leader: int = 0
    rounds_left: int = 0
    most_still_available: int = 0
    secures_position: int | None = None
    already_secured: bool = False
    out_of_reach: bool = False
    live_rivals: list[str] = field(default_factory=list)

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
        if self.already_secured:
            return "The championship is already yours."
        if self.out_of_reach:
            return "The championship is gone; this is for the placing."
        if not self.live_rivals:
            return "Nobody left can catch you."
        if self.secures_position:
            return (f"P{self.secures_position} today secures it, whatever "
                    f"they do.")
        where = ("leading by %d" % self.margin_to_leader if self.leading
                 else "%d behind" % -self.margin_to_leader)
        return (f"Nothing settles it today - {where}, "
                f"{self.most_still_available} still on the table.")

    def matters_here(self, on_the_grid) -> list[str]:
        """The title rivals who are actually in THIS race.

        Everybody else on the board is a place, not a championship. Defending
        against a driver who cannot take the title costs the race being driven
        for one that is not in danger.
        """
        here = {str(name) for name in (on_the_grid or ())}
        return [name for name in self.live_rivals if name in here]


def title_math(table: list[Standing], *, ours: str,
               rounds_left: int, scheme=None,
               pole_points: int = 0, fastest_lap_points: int = 0,
               field_size: int | None = None) -> TitleMath:
    """What we must finish to secure it, and who can still take it.

    The rival set is the honest part. **Only a driver who could still pass us
    if he won everything left is a title rival**; everybody else is racing for
    a place, and telling the driver to defend against them costs him the race
    he is actually in.
    """
    points = resolve_scheme(scheme)
    per_race_max = (points[0] if points else 0) + pole_points \
        + fastest_lap_points
    available = max(0, rounds_left) * per_race_max

    mine = next((s for s in table if s.driver == ours), None)
    out = TitleMath(leader=table[0].driver if table else None, ours=ours,
                    our_points=mine.points if mine else 0,
                    rounds_left=max(0, rounds_left),
                    most_still_available=available)
    if mine is None or not table:
        return out

    others = [s for s in table if s.driver != ours]
    out.margin_to_leader = mine.points - table[0].points
    out.live_rivals = [s.driver for s in others
                       if s.points + available > mine.points]

    if not out.live_rivals and available >= 0:
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
        out.secures_position = 1 if not points else None
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
