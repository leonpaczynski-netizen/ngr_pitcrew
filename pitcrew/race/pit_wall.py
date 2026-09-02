"""The live pit wall: who is in the lane, on what, with how much.

Everything under `telemetry/` can read a board. Nothing was watching one. This
is the thing that runs during a race, on the frames the wear sampler already
grabs, and turns them into stops with a driver's name on them.

### It rides on someone else's grab, and it has to

Measured on this machine, `mss` costs about 16.6 ms for a grab of ANY size -
that is the vsync, not the copy - and it does not compose: four regions is four
grabs and 15 Hz. So a second sampler with its own grab would halve the wear
gauge's rate to read a board that changes once a lap. `see` therefore takes a
frame somebody else already has, locates the board ONCE with
`board.flag_ladder`, and hands that one result to both readers.

### Why it must be running, and cannot be asked afterwards

**The pit columns mark the car standing in the box at that instant.** Measured
across a whole race, of 94 clean frames after CruisingChaos filled from 10 L to
89, exactly one carried columns - and it belonged to a different car, in the
lane at that moment. A driver who stopped five minutes ago looks identical on
screen to one who has never stopped.

So entry fuel exists only while the car is standing. There is no later question
that recovers it, which is the whole reason this class exists rather than a
post-race pass over a recording.

### A late first reading is a floor, not a figure

If the watcher joins a stop after the fill has begun, the lowest figure it saw
is not the entry fuel - it is an upper bound on it, and the litres taken come
out too small. That cannot be detected from the numbers themselves, so every
stop carries `reads` and the seconds it was watched, and `partial` says the
watcher never saw the car outside the lane before the fill. CLAUDE.md rule 5:
what is inferred says so.

### Nothing here may reach the race path

Every failure is caught and swallowed. A frame that cannot be read is not an
absence - it is silence, and silence must not close a stop that is still going
on, or a car gets an exit figure from the middle of its own fill.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from pitcrew.diagnostics import log
from pitcrew.race.rivals import Stop
from pitcrew.telemetry.board import flag_ladder, own_row
from pitcrew.telemetry.hud_digits import read_fuel
from pitcrew.telemetry.pit_columns import read_rows
from pitcrew.telemetry.roster import ROW_MATCH_TOL, Roster
from pitcrew.telemetry.roster import read as read_rows_of_board

_log = log(__name__)

# Clean frames in a row without this car's columns before its stop is closed.
# **Clean frames, not elapsed frames.** A frame the board could not be read on
# says nothing about whether a car is in the lane, and counting it as absence
# closes a stop in the middle of its own fill.
CLOSE_AFTER_CLEAN_FRAMES = 3

# Below this many fuel readings a stop is not worth filing: one reading cannot
# distinguish an entry figure from an exit one.
MIN_READS = 2

# A driver must be seen this many times before he is a driver rather than a
# misread. See `Roster.drivers`.
MIN_SIGHTINGS = 20


@dataclass
class Visit:
    """One car's time in the pit lane, as it is being watched."""
    driver: int
    lap: int | None
    started_s: float
    readings: list[int] = field(default_factory=list)
    last_s: float = 0.0
    # True where the car was already showing columns the first time this
    # watcher managed to read the board - so the fill may have begun unseen.
    partial: bool = False

    @property
    def entry_l(self) -> int | None:
        return min(self.readings) if self.readings else None

    @property
    def exit_l(self) -> int | None:
        return max(self.readings) if self.readings else None

    def as_stop(self) -> Stop:
        return Stop(lap=self.lap,
                    fuel_in_l=(float(self.entry_l)
                               if self.entry_l is not None else None),
                    fuel_out_l=(float(self.exit_l)
                                if self.exit_l is not None else None))


@dataclass(frozen=True)
class Seen:
    """A finished stop, with the evidence behind it. CLAUDE.md rule 4."""
    driver: str | None
    driver_id: int
    stop: Stop
    reads: int
    watched_s: float
    partial: bool


class PitWall:
    """Who is on the board, who is in the lane, and what their stop cost.

    Built once per session and reset between them. CLAUDE.md rule 11: the
    roster, the visits and the positions all describe one race, and a race that
    opens holding the last one's is a race that reports it.
    """

    def __init__(self, roster: Roster | None = None, *, on_stop=None) -> None:
        self._roster = roster if roster is not None else Roster()
        self._on_stop = on_stop
        self._visits: dict[int, Visit] = {}
        self._absent: dict[int, int] = {}
        self._position: dict[int, int] = {}
        self._pitted: set[int] = set()
        self._stops: list[Seen] = []
        self._frames = 0
        self._clean = 0

    # --- lifecycle ------------------------------------------------------

    def new_session(self) -> None:
        """Forget the last race. Everything here is about one of them.

        The roster is kept: driver identities are the one thing that SHOULD
        cross a session boundary, and it is seeded from the archive anyway.
        """
        self._visits.clear()
        self._absent.clear()
        self._position.clear()
        self._pitted.clear()
        self._stops = []
        self._frames = self._clean = 0

    @property
    def roster(self) -> Roster:
        return self._roster

    def stops(self) -> list[Seen]:
        return list(self._stops)

    def positions(self) -> dict[str, int]:
        """Board position per named driver, best effort."""
        out = {}
        for driver, place in self._position.items():
            name = self._roster.name_of(driver)
            if name:
                out[name] = place
        return out

    def has_pitted(self, driver_id: int) -> bool:
        """Whether this car has been seen in the lane THIS session.

        A latch, not a reading: the columns are gone the moment he leaves, so
        asking the screen later answers a different question.
        """
        return driver_id in self._pitted

    # --- the frame ------------------------------------------------------

    def see(self, frame, *, lap: int | None = None, now: float | None = None):
        """Take one frame. Never raises; returns the stops it just closed."""
        try:
            return self._see(frame, lap, now if now is not None
                             else time.monotonic())
        except Exception:                      # pragma: no cover - belt
            _log.exception("pit-wall: frame not processed")
            return []

    def _see(self, frame, lap, now):
        self._frames += 1
        ladder = flag_ladder(frame)
        if not ladder:
            return []                     # silence, not absence
        board = own_row(frame)
        if board is None:
            return []
        rows = read_rows_of_board(frame, board, ladder)
        if not rows:
            return []
        self._clean += 1

        ids: dict[int, int] = {}
        for place, row in enumerate(rows, start=1):
            driver = self._roster.see(row.name)
            if driver is None:
                continue
            ids[row.y] = driver
            self._position[driver] = place

        in_lane: set[int] = set()
        for pit in read_rows(frame, board, ladder):
            if not pit.fuel_box:
                continue
            near = [y for y in ids if abs(y - pit.y) <= ROW_MATCH_TOL]
            if not near:
                continue
            driver = ids[near[0]]
            in_lane.add(driver)
            # **The columns being drawn is the fact; the digits are a reading
            # of it.** These are two different questions and an earlier version
            # answered only the second, so a car whose fuel number could not be
            # transcribed was recorded as never having pitted at all. The
            # presence of the columns needs no transcription - see
            # `pit_columns.has_pitted` - and it is the half that decides
            # whether a stop is happening.
            self._pitted.add(driver)
            self._absent[driver] = 0
            visit = self._visits.get(driver)
            if visit is None:
                # Seen in the lane on the first clean frame of the session
                # means the fill may already have been running.
                visit = Visit(driver=driver, lap=lap, started_s=now,
                              partial=self._clean <= 1)
                self._visits[driver] = visit
            visit.last_s = now
            x0, y0, x1, y1 = pit.fuel_box
            litres = read_fuel(frame[y0:y1 + 1, x0:x1 + 1])
            if litres is not None:
                visit.readings.append(litres)

        closed = []
        for driver in list(self._visits):
            if driver in in_lane:
                continue
            self._absent[driver] = self._absent.get(driver, 0) + 1
            if self._absent[driver] >= CLOSE_AFTER_CLEAN_FRAMES:
                done = self._close(driver)
                if done is not None:
                    closed.append(done)
        return closed

    def close_all(self) -> list[Seen]:
        """End every open visit, for the end of a session."""
        return [s for s in (self._close(d) for d in list(self._visits))
                if s is not None]

    def _close(self, driver: int) -> Seen | None:
        visit = self._visits.pop(driver, None)
        self._absent.pop(driver, None)
        if visit is None or len(visit.readings) < MIN_READS:
            return None
        seen = Seen(driver=self._roster.name_of(driver), driver_id=driver,
                    stop=visit.as_stop(), reads=len(visit.readings),
                    watched_s=max(0.0, visit.last_s - visit.started_s),
                    partial=visit.partial)
        self._stops.append(seen)
        _log.info("pit-wall: %s stopped - in %s L, out %s L, %d reads over "
                  "%.0f s%s", seen.driver or f"driver {driver}",
                  visit.entry_l, visit.exit_l, seen.reads, seen.watched_s,
                  " (joined mid-fill)" if seen.partial else "")
        if self._on_stop is not None:
            try:
                self._on_stop(seen)
            except Exception:               # pragma: no cover - belt
                _log.exception("pit-wall: stop handler failed")
        return seen

    # --- naming ---------------------------------------------------------

    def named(self, min_sightings: int = MIN_SIGHTINGS) -> list[tuple[int, str]]:
        """Driver ids that are worth a name, commonest first.

        The ones with no name yet are the ones a person has to label once. A
        proportional mixed-case font is not something this app guesses at.
        """
        return [(d, self._roster.name_of(d) or "")
                for d in self._roster.drivers(min_sightings=min_sightings)]
