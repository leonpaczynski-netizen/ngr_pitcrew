"""Who he actually races here, read off the replay after the race.

**Live rival vision in VR is refused on evidence, not on effort.** GT7 draws
its HUD on the car's dashboard in 3D, so it moves with head position - measured
at roughly 200 px of drift - and the *wear gauge*, which is large, high
contrast and fixed in the car, reads 6 crossings in 22. The proximity radar is
smaller, translucent and drawn over moving scenery.

And the two are not the same problem. Wear changes slowly, so occasional
samples suffice. **Rival proximity changes in a second**, so occasional samples
of it are not a degraded signal, they are no signal. That is why rivals moved
from perception to memory: read off the replay afterwards, handed to George as
a briefing before the next race.

### What a tendency is, and what it is not

`tools/read_replay_traffic.py` fills `traffic` with presence and side - who was
there, on which side, for how long - and is deliberate that **the distance is
in ribbon pixels and not in metres**, because the ribbon narrows toward its
ends and a metre figure would be one the tool invented.

So a tendency here is about *time spent together*, which is what the data
supports. It is not a gap, not a closing speed and not a prediction of when
anyone will stop - none of those are in the traffic table and inventing one
would be exactly the confident wrong answer this whole layer exists to avoid.

The record is `[{"rival": ..., "tendency": ...}]`, in words, because it is read
by a person at the desk and by nothing else. George's rules do not consume it -
they consume the numbers in the rest of the briefing.
"""
from __future__ import annotations

from dataclasses import dataclass

# Laps spent inside radar range before a rival is worth naming. Below this it
# is one overtake, which every race has and none of them is a tendency.
MIN_LAPS_TOGETHER = 3


@dataclass(frozen=True)
class Rival:
    """One driver, and how much of a race was spent beside him."""
    name: str
    laps_ahead: int
    laps_behind: int
    laps_together: int

    @property
    def mostly(self) -> str:
        if self.laps_ahead > self.laps_behind * 2:
            return "ahead"
        if self.laps_behind > self.laps_ahead * 2:
            return "behind"
        return "either side"

    def as_record(self) -> dict:
        """The shape `race_knowledge.rivals_json` holds."""
        return {"rival": self.name, "tendency": self.describe()}

    def describe(self) -> str:
        laps = f"{self.laps_together} lap{'' if self.laps_together == 1 else 's'}"
        if self.mostly == "either side":
            return f"raced him for {laps}, both sides"
        return f"raced him for {laps}, mostly {self.mostly}"


def tendencies(store, session_id: int) -> list[Rival]:
    """Who was near him in this session, in order of time spent together.

    Rows with no name are skipped rather than counted as one driver. **The
    board pass is what supplies names** and it is a separate, operator-assisted
    step, so lumping the unnamed together would report a phantom who was
    everywhere.

    **Read off the board, and off the radar only where there is no board.**
    The radar sees about a second in each direction and only while the driver
    has that page up: on the Daytona league race it produced 2 contacts from
    595 samples, neither placeable, because he was never closer than 1.2 s to
    anyone and spent the last laps 25 s clear. The board, on the same capture,
    gave 1,096 readings of who was either side of him. A tendency is about
    time spent together, and the board is the instrument that measures it.
    """
    rows = [{"name": row["driver"], "side": row["side"],
             "lap_num": row["lap_num"]}
            for row in store.list_board_sightings(session_id)]
    if not rows:
        rows = [{"name": row["rival"], "side": row["side"],
                 "lap_num": row["lap_num"]}
                for row in store.list_traffic(session_id)]
    seen: dict[str, dict[str, set]] = {}
    for row in rows:
        name = row["name"]
        if not name:
            continue
        side = row["side"] or "unknown"
        lap = row["lap_num"]
        if lap is None:
            continue
        entry = seen.setdefault(name, {"ahead": set(), "behind": set(),
                                       "unknown": set()})
        entry.setdefault(side, set()).add(lap)

    found = []
    for name, sides in seen.items():
        ahead, behind = sides.get("ahead", set()), sides.get("behind", set())
        together = ahead | behind | sides.get("unknown", set())
        if len(together) < MIN_LAPS_TOGETHER:
            continue
        found.append(Rival(name, len(ahead), len(behind), len(together)))
    return sorted(found, key=lambda one: -one.laps_together)


def carry_into_knowledge(store, event_id: int, session_id: int, *,
                         author: str = "replay traffic pass") -> list[dict]:
    """Fit this race's rivals and write them into the circuit's briefing.

    Written against the **event**, not the circuit: pit loss and the tow are
    track constants, but who he was racing belongs to one round of one league,
    and next season's grid is a different set of names.
    """
    from dataclasses import replace as _replace

    from pitcrew.analysis.resolve import circuit_key
    from pitcrew.race.knowledge import Knowledge
    from pitcrew.store.db import _now

    event = store.get_event(event_id)
    if event is None or not event.get("track"):
        return []
    found = tendencies(store, session_id)
    if not found:
        return []

    key = circuit_key(event["track"], event.get("layout"))
    base = store.get_race_knowledge(key, event_id)
    if base is None or base.event_id != event_id:
        # The circuit-wide record is not this race's, so a new one is opened
        # rather than the constants being overwritten with one race's grid.
        base = Knowledge(circuit_key=key, event_id=event_id)
    records = [one.as_record() for one in found]
    store.save_race_knowledge(_replace(base, rivals=tuple(records),
                                       author=author, written_at=_now()))
    return records
