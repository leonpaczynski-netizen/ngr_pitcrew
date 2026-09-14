"""Who has been seen standing in the pit lane this race, and what was said.

The pit wall sees a rival's stop while it is happening and never again. This
is the race's record of those stops as NEWS: which have been told to the
driver, which have gone stale untold, which cars are in the lane right now,
and which of the places he gained were really cars in the lane.

### Why a record and not a queue (Bathurst, 14 Sep 2026)

**Eight of ten rival stops were never spoken.** The entries were a queue on
`RaceState`, drained at EVERY crossing whether or not a rival call won it -
and at the crossings that mattered a box call did win, so three stops went
into the lap-10 crossing and came out of it unsaid, and three more into lap
11. Two cars in one frame then tied on severity and the second was dropped.

A stop is now retired in exactly two ways: **it was said**, or **it went
stale** - the car has left the lane and a whole lap has been driven since
without a chance to say it. Nothing else removes one.

### What stale means, exactly

`left_lap` is our completed-lap count when his finished stop was filed.
Filed while we are driving lap `left_lap + 1`; the crossing that completes it
is still a chance to say it; the crossing after that (`lap >= left_lap + 2`)
is not, because by then he has been back on the circuit for at least a lap
and "he has boxed" is history rather than news. A stop that is never filed at
all - the car left the visible board and the wall's own clock has not closed
it yet - is retired after `STALE_AFTER_LAPS` laps from the lap it began on, as
a belt: the wall closes a silent visit within three minutes.

### Threads

Entries are added and filed on the Qt thread (`coordinator.note_rival_*`);
they are TOLD from the Qt thread at a crossing and from the telemetry thread
mid-lap. So nothing here removes from the list while it can be read: telling
and explaining are set insertions, and every reader walks a copy. Rule 11:
`new_session` empties all of it, and the coordinator calls it on arming.

### What this is for next

A later pass volunteers "two ahead still to stop" and "effectively P8 after
the stops". Both need exactly this: who has stopped, when, whether he was
ahead of us when he went in, and whether he is still in there.
"""
from __future__ import annotations

from dataclasses import dataclass

# Laps after the lap a stop BEGAN on past which an entry that was never
# filed as finished is no longer news. See the module docstring.
STALE_AFTER_LAPS = 3

# The separator between stop keys inside a call's tag. A driver name that
# carries one has it replaced, so a tag always splits back into its keys.
_SEP = "|"


@dataclass
class LaneStop:
    """One rival's visit to the lane, as the coordinator was told of it."""
    key: str
    driver: str
    # Our completed-lap count when the wall saw the visit begin.
    lap: int | None
    fuel_in_l: float | None
    # The entry figure is an upper bound: nobody saw him arrive.
    partial: bool
    # Whether he was ahead of us on the board the last time he was seen
    # OUT of the lane. `None` where either place was unread.
    ahead_at_entry: bool | None
    # Our lap count when the coordinator was told. Used where `lap` is None.
    noted_lap: int
    # Our lap count when his finished stop was filed, or None - still in.
    left_lap: int | None = None


class LaneLog:
    """The race's rival stops, until each has been said or gone stale."""

    def __init__(self) -> None:
        self._stops: list[LaneStop] = []
        self._told: set[str] = set()
        self._explained: set[str] = set()
        self._returned: set[str] = set()

    # --- lifecycle ------------------------------------------------------

    def new_session(self) -> None:
        """CLAUDE.md rule 11: a stop is news about one race."""
        self._stops = []
        self._told = set()
        self._explained = set()
        self._returned = set()

    @staticmethod
    def key_of(driver: str, lap: int | None) -> str:
        return f"{str(driver).replace(_SEP, '/')}@{lap}"

    def enter(self, entered, *, lap: int) -> LaneStop | None:
        """A rival confirmed standing in his box. Returns the new record, or
        None where this visit is already on file or carries no name."""
        driver = getattr(entered, "driver", None)
        if not driver:
            return None
        visit_lap = getattr(entered, "lap", None)
        key = self.key_of(driver, visit_lap)
        if any(stop.key == key for stop in list(self._stops)):
            return None
        fuel = getattr(entered, "fuel_in_l", None)
        stop = LaneStop(
            key=key, driver=str(driver), lap=visit_lap,
            fuel_in_l=float(fuel) if fuel is not None else None,
            partial=bool(getattr(entered, "partial", False)),
            ahead_at_entry=getattr(entered, "ahead_at_entry", None),
            noted_lap=int(lap))
        self._stops = self._stops + [stop]
        return stop

    def left(self, driver: str | None, *, lap: int) -> LaneStop | None:
        """His finished stop was filed: he is out of the lane."""
        if not driver:
            return None
        for stop in reversed(list(self._stops)):
            if stop.driver == driver and stop.left_lap is None:
                stop.left_lap = int(lap)
                return stop
        return None

    # --- what can still be said -----------------------------------------

    def stale(self, stop: LaneStop, lap: int) -> bool:
        if stop.left_lap is not None:
            return lap >= stop.left_lap + 2
        began = stop.lap if stop.lap is not None else stop.noted_lap
        return lap >= began + STALE_AFTER_LAPS

    def untold(self, lap: int) -> list[LaneStop]:
        """Stops not yet said and still news, in the order they were seen."""
        return [stop for stop in list(self._stops)
                if stop.key not in self._told and not self.stale(stop, lap)]

    def tell(self, keys) -> None:
        self._told.update(keys)

    def told(self, key: str) -> bool:
        return key in self._told

    @staticmethod
    def tag_for(prefix: str, stops) -> str:
        return prefix + ":" + _SEP.join(stop.key for stop in stops)

    @staticmethod
    def keys_in_tag(prefix: str, tag: str | None) -> list[str]:
        head = prefix + ":"
        if not tag or not tag.startswith(head):
            return []
        return [key for key in tag[len(head):].split(_SEP) if key]

    # --- what the board's position byte is really saying ----------------

    def in_the_lane(self) -> list[LaneStop]:
        return [stop for stop in list(self._stops) if stop.left_lap is None]

    def passed_in_the_lane(self) -> list[LaneStop]:
        """Cars in the lane now that were ahead of us when they went in, and
        that no place call has been explained by yet."""
        return [stop for stop in self.in_the_lane()
                if stop.ahead_at_entry is True
                and stop.key not in self._explained]

    def explain(self, keys) -> None:
        self._explained.update(keys)

    def explained(self, key: str) -> bool:
        return key in self._explained

    def back_out(self, lap: int) -> list[LaneStop]:
        """Cars a place call already said were in the lane, now out of it
        within the last lap, and not yet used to explain a place lost."""
        return [stop for stop in list(self._stops)
                if stop.key in self._explained
                and stop.key not in self._returned
                and stop.left_lap is not None and lap <= stop.left_lap + 1]

    def returned(self, keys) -> None:
        self._returned.update(keys)
