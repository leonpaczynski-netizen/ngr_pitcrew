"""Where the teammate is, and what can honestly be said about working with him.

One driver on the board is flagged as the teammate. This says what is knowable
about him at any moment, and it is deliberately a short list, because the race
HUD is generous about some things and silent about others.

### What the screen gives, and what it withholds

**Position: always.** He is a row on the board and the board is in race order,
so his place and the number of cars between us are exact, every frame.

**Separation in seconds: only when he is next to us.** GT7 draws three gap
readouts and only three - to the car ahead, to the leader, to the car behind.
A teammate two places up has no number on him at all. This is the single
biggest limit here and it is not worked around: an interval to a car that is
not adjacent would have to be integrated from lap times, and this driver's own
lap-to-lap noise is 0.918 s, so a figure built that way would be worse than
saying nothing. `separation_s` returns `None` and says why.

**Fuel, compound and pit status: only while he is actually in the lane.**
Measured across a whole race, the pit columns mark the car standing in the pit
box at that moment and are gone again afterwards - a driver who stopped five
minutes ago looks exactly like one who has not stopped at all. So `pitted` and
`stop` have to be caught as they happen and carried forward by the caller;
asking the screen later gets nothing.

**And only if he is in the top eight.** Every clean frame of the measured race
showed eight rows, positions 1 to 8. A teammate running ninth is not on the
board, `position` is `None`, and `where_is_he` returns nothing rather than
guessing - which is the honest answer, but it does mean this goes quiet exactly
when a teammate is having a bad race.

### Why there are no team orders in here

Working with a teammate in a league with no pit-to-pit radio comes down to
three things that are all facts rather than instructions: where he is, whether
he has stopped, and whether he has the fuel to finish. What to do about it is
the driver's call and his teammate's, made between them before the race. This
module does not invent a strategy for two cars, and in particular it never
tells him to hold station or to let anybody past.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.rivals import Stop

# A teammate this many places away or fewer is close enough that what he does
# changes what we should do. Beyond it he is racing a different race.
NEARBY_PLACES = 3


@dataclass(frozen=True)
class Teammate:
    """The teammate as the board shows him, plus what the caller has remembered.

    Every field is nullable and means "not seen" when it is `None`.

    **`pitted` is a latch, not a reading.** It was written believing the pit
    columns stayed on a car's row once it had stopped; measured over a whole
    race they do not - they mark the car standing in the box at that instant and
    vanish afterwards, so a driver who stopped five minutes ago is
    indistinguishable on screen from one who has never stopped. Whoever fills
    this in must set it when the columns are seen and keep it set, because
    reading it fresh off a later frame answers a different question. Left
    `False` by a caller that has been watching, it means he has not been in the
    lane; `False` from a caller that has just started watching means nothing at
    all, and this class cannot tell those apart.
    """
    name: str
    position: int | None = None
    ours: int | None = None
    pitted: bool = False
    stop: Stop | None = None

    @property
    def places_away(self) -> int | None:
        if self.position is None or self.ours is None:
            return None
        return abs(self.position - self.ours)

    @property
    def ahead(self) -> bool | None:
        if self.position is None or self.ours is None:
            return None
        return self.position < self.ours

    @property
    def nearby(self) -> bool:
        places = self.places_away
        return places is not None and places <= NEARBY_PLACES


def separation_s(mate: Teammate, gap_ahead_s: float | None,
                 gap_behind_s: float | None) -> tuple[float | None, str]:
    """Seconds between us, and where the figure came from.

    **`None` unless he is the car immediately ahead or behind.** GT7 publishes
    three gaps and no others, so any interval to a teammate further away would
    have to be built from lap times - and at 0.918 s of lap-to-lap noise that
    is a worse answer than none. The reason travels with the number so a caller
    cannot mistake "not adjacent" for "level with you".
    """
    places = mate.places_away
    if places is None:
        return None, "he is not on the board"
    if places != 1:
        return None, "the screen only carries a gap to the car next to you"
    if mate.ahead and gap_ahead_s is not None:
        return gap_ahead_s, "gap to the car ahead"
    if mate.ahead is False and gap_behind_s is not None:
        return gap_behind_s, "gap to the car behind"
    return None, "the gap was not drawn"


def fuel_to_the_flag(mate: Teammate, laps_left: int | None,
                     burn_per_lap_l: float | None) -> bool | None:
    """Whether his tank reaches the end. `None` where it was not read.

    An unread tank is not a full one, and it is not an empty one either.
    """
    if mate.stop is None or mate.stop.fuel_out_l is None:
        return None
    if not laps_left or not burn_per_lap_l or burn_per_lap_l <= 0:
        return None
    return mate.stop.fuel_out_l >= laps_left * burn_per_lap_l


def where_is_he(mate: Teammate) -> str | None:
    """One sentence on where the teammate is, or `None` if he is not on screen.

    Positions, not instructions. What two drivers do about being near each
    other is theirs to agree beforehand.
    """
    if mate.position is None:
        return None
    places = mate.places_away
    if places is None:
        return "%s is P%d." % (mate.name, mate.position)
    if places == 0:
        return "%s is P%d, same as you." % (mate.name, mate.position)
    where = "ahead" if mate.ahead else "behind"
    return ("%s is P%d, %d place%s %s."
            % (mate.name, mate.position, places,
               "" if places == 1 else "s", where))


def status(mate: Teammate, *, laps_left: int | None = None,
           burn_per_lap_l: float | None = None,
           gap_ahead_s: float | None = None,
           gap_behind_s: float | None = None) -> list[str]:
    """Everything honestly knowable about the teammate right now.

    Facts in the order they are useful, and silence where the screen is silent.
    """
    lines: list[str] = []
    place = where_is_he(mate)
    if place is None:
        return lines
    seconds, _ = separation_s(mate, gap_ahead_s, gap_behind_s)
    if seconds is not None:
        place = place[:-1] + ", %.1f seconds %s." % (
            abs(seconds), "up the road" if mate.ahead else "back")
    lines.append(place)

    if not mate.pitted:
        lines.append("He has not stopped yet.")
        return lines

    reaches = fuel_to_the_flag(mate, laps_left, burn_per_lap_l)
    if reaches is True:
        lines.append("He has stopped and has the fuel to finish.")
    elif reaches is False:
        lines.append("He has stopped but is short of the flag, so he has to "
                     "come in again.")
    else:
        lines.append("He has stopped. His tank was not readable.")
    return lines
