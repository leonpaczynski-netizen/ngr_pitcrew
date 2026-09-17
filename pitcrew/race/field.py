"""What everyone is doing - the tablet left of the wheel.

His three-screen split, 17 Sep 2026: the phone carries his car, the monitor
history, and the tablet *"what's going on around me and other car data"* -
*"I want to see what everyone is doing here: on lap they pitted, how much fuel
in and out, and prediction on one or two stop"*, led by the timing tower.

### What it can honestly be

**GT7's feed carries this car and nothing else** (CLAUDE.md §3). Every other
car here was read off GT7's own timing board and pit columns on screen - the
board about every two seconds, and only the rows GT7 draws (about eight). So:

* a car the board never showed has no row; nothing is guessed about it;
* a place is the board's, and carries how old the read is;
* **a gap exists only for the two cars either side of us**, because only they
  have an interval box on his screen;
* a fuel figure is the pit column's, and **an exit figure is often a lower
  bound** - a car drops off the visible board while it stands, and the visit
  is closed on the clock with the highest reading anyone got. Marked, never
  passed off as the fill.

### The stop prediction is George's own arithmetic

`rival_calls.fuel_shortfall` - his measured burn where the wall has watched
him, ours where it has not, and the reading error that grows with the laps
still to run - is the expression the "short to the flag" and "has to stop
again" calls are made from. The tablet reads the same one, so the screen and
the voice cannot disagree about a car (rule 12), and it names whose burn it
used. **A car a few per cent light drives it out rather than stopping**
(`SAVEABLE_FRACTION`), which is why "short" and "stops again" are different
words here.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.news import SAMPLE_HZ
from pitcrew.race.rival_calls import Rival, fuel_shortfall

# The prediction, as the tablet words it. Each is a claim of a different
# strength, and they are kept apart for that reason (rule 13).
REACHES_FLAG = "reaches the flag"
SHORT_SAVES = "short - can save it"
STOPS_AGAIN = "stops again"
NO_STOP_SEEN = "no stop seen"
CANNOT_TELL = "can't tell"

# How old a board read may be before the places are marked as a moment behind.
BOARD_FRESH_S = 6.0


@dataclass(frozen=True)
class Prediction:
    """One car's stop picture: what he has done, and what his fuel says."""
    stops_seen: int
    words: str
    # How many stops the race comes to for him, where the fuel says: the ones
    # seen, plus one if he must come in again. None where it cannot say.
    total_stops: int | None = None
    # The last lap his exit fuel reaches, where he must stop again.
    reaches_lap: int | None = None
    # Why it cannot say, where it cannot.
    why: str | None = None
    # Whose burn the arithmetic used: "his" or "ours".
    burn_of: str | None = None
    # The shortfall is inside what two readings and a burn can resolve.
    unconfirmed: bool = False


@dataclass(frozen=True)
class Car:
    """One row: only what is known about this car."""
    name: str | None
    place: int | None = None
    us: bool = False
    gap_s: float | None = None
    in_lane: bool = False
    last_stop_lap: int | None = None
    fuel_in_l: float | None = None
    fuel_out_l: float | None = None
    # The exit figure is the highest reading, not the fill (see module note).
    out_is_bound: bool = False
    prediction: Prediction | None = None


@dataclass(frozen=True)
class FieldView:
    rows: tuple[Car, ...] = ()
    # Age of the board read the places came from; None where none was read.
    board_age_s: float | None = None
    position: int | None = None
    field_size: int | None = None
    lap: int | None = None
    laps_total: int | None = None
    why: str | None = None


def predict(rival: Rival | None, *, stops_seen: int, our_burn_l: float | None,
            laps_total: int | None) -> Prediction:
    """The stop picture for one car, from `fuel_shortfall` and nothing else."""
    if rival is None or rival.stop is None:
        return Prediction(stops_seen=stops_seen,
                          words=NO_STOP_SEEN if stops_seen == 0 else CANNOT_TELL,
                          why=None if stops_seen == 0 else "no fuel read at his stop")
    burn_of = "his" if rival.burn_per_lap_l else "ours"
    if rival.exit_is_a_bound:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="his exit fuel is only a lower bound",
                          burn_of=burn_of)
    if laps_total is None:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="no race length", burn_of=burn_of)
    short = fuel_shortfall(rival, our_burn_l, laps_total=laps_total)
    if short is None:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="no fuel or burn to reckon with", burn_of=burn_of)
    if short.litres <= 0:
        return Prediction(stops_seen=stops_seen, words=REACHES_FLAG,
                          total_stops=stops_seen, burn_of=burn_of,
                          unconfirmed=not short.certain)
    if short.saveable:
        return Prediction(stops_seen=stops_seen, words=SHORT_SAVES,
                          total_stops=stops_seen, burn_of=burn_of,
                          unconfirmed=not short.certain)
    burn = rival.burn_per_lap_l or our_burn_l
    reaches = rival.stop.lap + int(rival.stop.fuel_out_l / burn)
    return Prediction(stops_seen=stops_seen, words=STOPS_AGAIN,
                      total_stops=stops_seen + 1, reaches_lap=reaches,
                      burn_of=burn_of, unconfirmed=not short.certain)


def field_view(state, board, *, packet: int | None) -> FieldView:
    """Everyone the app knows about, as of now.

    `board` is `RaceNews.board()` - the last board read, as places by name -
    or None. Pure: given a race state and a board, so it tests without a race.
    """
    if state is None:
        return FieldView(why="no race running")
    ours = getattr(state, "position", None)
    base = dict(position=ours, field_size=getattr(state, "field_size", None),
                lap=getattr(state, "lap", None),
                laps_total=getattr(state, "laps_total", None))
    lane = getattr(state, "lane", None)
    rivals = dict(getattr(state, "rivals", None) or {})
    our_burn = getattr(state, "fuel_per_lap_l", None)
    laps_total = base["laps_total"]

    places: dict[str, int] = dict(getattr(state, "rival_positions", None) or {})
    age = None
    if board is not None:
        places.update(board.places)           # the fresher read wins
        if packet is not None:
            age = max(0.0, (int(packet) - int(board.packet)) / SAMPLE_HZ)
    standing = {str(stop.driver).lower()
                for stop in (lane.in_the_lane() if lane is not None else [])}

    names = set(places) | set(rivals)
    rows: list[Car] = []
    for name in names:
        place = places.get(name)
        if ours and place == int(ours):
            # **Our own row is ours, whatever the board named it** - the place
            # comes off the packet, 60 times a second.
            continue
        rival = rivals.get(name)
        stop = rival.stop if rival is not None else None
        seen = len(lane.visits_by(name)) if lane is not None else 0
        if rival is not None and rival.pitted:
            seen = max(seen, 1)
        rows.append(Car(
            name=name, place=place,
            in_lane=str(name).lower() in standing,
            last_stop_lap=getattr(stop, "lap", None),
            fuel_in_l=getattr(stop, "fuel_in_l", None),
            fuel_out_l=getattr(stop, "fuel_out_l", None),
            out_is_bound=bool(getattr(rival, "exit_is_a_bound", False)),
            prediction=predict(rival, stops_seen=seen, our_burn_l=our_burn,
                               laps_total=laps_total)))
    if ours:
        gaps = {}
        for side, step in (("ahead", -1), ("behind", 1)):
            trend = getattr(state, f"gap_{side}", None)
            seconds = trend.latest() if trend is not None else None
            if seconds is not None:
                gaps[int(ours) + step] = seconds
        rows = [row if row.place not in gaps
                else Car(**{**row.__dict__, "gap_s": gaps[row.place]})
                for row in rows]
        rows.append(Car(name=None, place=int(ours), us=True))
    # By place; a car with no place (his stop was read, his row never was)
    # goes to the bottom rather than being given one.
    rows.sort(key=lambda row: (row.place is None, row.place or 0,
                               str(row.name or "")))
    return FieldView(rows=tuple(rows), board_age_s=age, **base)
