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
from pitcrew.race.gaps import GapTrend, read_gaps
from pitcrew.race.rivals import Stop
from pitcrew.telemetry.board import flag_ladder, own_row
from pitcrew.telemetry.compound import read as read_compound
from pitcrew.telemetry.hud_digits import read_fuel
from pitcrew.telemetry.pit_columns import read_rows
from pitcrew.telemetry.roster import ROW_MATCH_TOL, Roster
from pitcrew.telemetry.roster import read as read_rows_of_board

_log = log(__name__)

# Frames in a row on which this car was SEEN ON THE BOARD without its columns,
# before its stop is closed.
#
# **Seen, not merely elapsed - and the difference cost four stops out of one.**
# Two things look like absence and only one of them is: a frame the board could
# not be read on, and a frame where the board read but this driver's own name
# did not. The second is common exactly when it hurts, because a car in its pit
# box is half behind a pit crew, which is one of the cases `Roster.drivers`
# names as a normal misread. Counting either as absence closes a stop in the
# middle of its own fill and opens a fresh one when the name comes back:
# measured over the whole Spa race, that turned one stop each for PUNISHED and
# the driver himself into four apiece, with burn rates to match.
CLOSE_AFTER_CLEAN_FRAMES = 3

# ...and a stop nobody has seen either way for this long is over. A car can
# leave the visible top eight while standing - `race/profile.py` has the
# measured account of why that is the normal case rather than the exception -
# and without a clock its visit would stay open to the flag. A GT7 stop is 50
# to 100 seconds of standing, so this is comfortably past the longest real one.
CLOSE_AFTER_SILENT_S = 180.0

# Below this many fuel readings a stop is not worth filing: one reading cannot
# distinguish an entry figure from an exit one.
MIN_READS = 2

# ...and below this many seconds it was not a stop at all. **The measured dead
# time before a hose is even connected is 16.9 s** - see `rivals.DEAD_TIME_S` -
# so nothing shorter than that can be a car standing in its box. Run over the
# whole Spa race without this, two 12-to-15 second fragments came back as
# stops, one of them with identical entry and exit fuel because it had caught
# the same number twice. Real stops in that race were watched for 87 to 117 s,
# so this discards fragments with a wide margin and no real stop near it.
MIN_WATCHED_S = 15.0

# A driver must be seen this many times before he is a driver rather than a
# misread. See `Roster.drivers`.
MIN_SIGHTINGS = 20

# ...and the compound letter needs this many agreeing frames. One frame is not
# a vote, and the tyre a rival fitted is a fact about his whole remaining race.
MIN_COMPOUND_READS = 2


@dataclass
class Visit:
    """One car's time in the pit lane, as it is being watched."""
    driver: int
    lap: int | None
    started_s: float
    readings: list[int] = field(default_factory=list)
    compounds: list[str] = field(default_factory=list)
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

    @property
    def compound(self) -> str | None:
        """The letter agreed on across this stop, or `None`.

        **A tie refuses, and it used to be decided by hash order.** Measured
        across eight values of PYTHONHASHSEED, `max(set(...), key=count)` on
        `['S','M','S','M']` returned S sometimes and M others: `set` iteration
        over strings is randomised per process, so replaying one recorded race
        twice filed a different tyre. A 2-2 split is the reader disagreeing
        with itself about a fact that describes a rival's whole remaining
        race, and an arbitrary winner is a confident answer where there is
        none.

        **And a vote of one is not a vote.** The fuel path has `MIN_READS` for
        exactly this reason; this had no floor at all.
        """
        if len(self.compounds) < MIN_COMPOUND_READS:
            return None
        tally: dict[str, int] = {}
        for code in self.compounds:
            tally[code] = tally.get(code, 0) + 1
        ranked = sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None
        return ranked[0][0]

    def as_stop(self) -> Stop:
        return Stop(lap=self.lap,
                    compound=self.compound,
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
    # **The FUEL readings and the COMPOUND readings are counted separately.**
    # They are two different claims from the same stop and a single `reads`
    # said nothing about which: a stop backed by forty fuel figures may have
    # had one legible disc, or none. CLAUDE.md rule 4.
    compound_reads: int
    watched_s: float
    partial: bool


class PitWall:
    """Who is on the board, who is in the lane, and what their stop cost.

    Built once per session and reset between them. CLAUDE.md rule 11: the
    roster, the visits and the positions all describe one race, and a race that
    opens holding the last one's is a race that reports it.
    """

    def __init__(self, roster: Roster | None = None, *, on_stop=None,
                 name_for=None) -> None:
        self._roster = roster if roster is not None else Roster()
        self._on_stop = on_stop
        # **Asked for a name at the moment a stop closes, not at the flag.** A
        # stop closes DURING the race, and whatever files it refuses a stop
        # with no driver on it - so a cluster the archive did not recognise had
        # its stop dropped, and naming the field afterwards was hours too late
        # for a fact that cannot be observed twice. `name_for()` returns a
        # provisional handle; the driver turns it into a person later, and
        # renaming carries the stops with it.
        self._name_for = name_for
        self._visits: dict[int, Visit] = {}
        self._absent: dict[int, int] = {}
        # Drivers seen on the board WITHOUT pit columns. A visit that begins
        # for a driver who is not in here started after the fill did, so far as
        # anything can tell - which is what `partial` means.
        self._seen_clean: set[int] = set()
        self._position: dict[int, int] = {}
        self._pitted: set[int] = set()
        self._stops: list[Seen] = []
        # The two intervals GT7 publishes either side of us, per lap. Kept as
        # trends rather than instants because a closing RATE is the cheapest
        # pace signal on the screen - see `race/gaps.py`.
        self.ahead = GapTrend(side="ahead")
        self.behind = GapTrend(side="behind")
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
        self._seen_clean.clear()
        self._position.clear()
        self._pitted.clear()
        self._stops = []
        self.ahead.new_session()
        self.behind.new_session()
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
            return self._close_stale(now)      # silence, not absence
        # **The ladder we already have, not a second search.** `own_row` finds
        # one itself when it is not given one, and this runs on the sampler's
        # worker thread where a duplicated O(n^2) scan over every saturated run
        # in a 1920x1080 frame comes straight out of the wear gauge's budget.
        board = own_row(frame, ladder=ladder)
        if board is None:
            return self._close_stale(now)
        rows = read_rows_of_board(frame, board, ladder)
        if not rows:
            return []
        self._clean += 1
        ids: dict[int, int] = {}
        identified: set[int] = set()
        for place, row in enumerate(rows, start=1):
            driver = self._roster.see(row.name)
            if driver is None:
                continue
            ids[row.y] = driver
            identified.add(driver)
            self._position[driver] = place

        in_lane: set[int] = set()
        for pit in read_rows(frame, board, ladder):
            if not pit.fuel_box:
                continue
            # The NEAREST row, not the first within tolerance: dict order is
            # insertion order, which is board order, so "first" quietly means
            # "highest up the screen".
            near = min((y for y in ids if abs(y - pit.y) <= ROW_MATCH_TOL),
                       key=lambda y: abs(y - pit.y), default=None)
            if near is None:
                continue
            driver = ids[near]
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
                # **Partial is about THIS driver, not about the session.** It
                # means nobody ever saw this car on the board without its
                # columns, so the fill may already have been running when the
                # watching began - which is the normal case for a car that
                # drops into the visible eight while it is already standing.
                visit = Visit(driver=driver, lap=lap, started_s=now,
                              partial=driver not in self._seen_clean)
                self._visits[driver] = visit
            visit.last_s = now
            x0, y0, x1, y1 = pit.fuel_box
            litres = read_fuel(frame[y0:y1 + 1, x0:x1 + 1])
            if litres is not None:
                visit.readings.append(litres)
            dx0, dy0, dx1, dy1 = pit.disc
            code = read_compound(frame[dy0:dy1 + 1, dx0:dx1 + 1])
            if code:
                visit.compounds.append(code)

        # **The gaps are noted AFTER the rows are identified**, so each trend
        # knows whose gap it is holding. A trend that does not know that
        # regresses straight through an overtake and reports the new car's
        # distance as our own lost pace.
        ahead_gap, behind_gap = read_gaps(frame, board)
        own_place = self._position.get(self._own_driver(ids, board))
        self.ahead.note(lap, ahead_gap,
                        subject=self._neighbour(ids, own_place, -1))
        self.behind.note(lap, behind_gap,
                         subject=self._neighbour(ids, own_place, +1))

        for driver in identified - in_lane:
            self._seen_clean.add(driver)

        closed = []
        for driver in list(self._visits):
            if driver in in_lane:
                continue
            if driver not in identified:
                # He was not on the board this frame, so this frame says
                # nothing about whether he is standing in his box.
                continue
            self._absent[driver] = self._absent.get(driver, 0) + 1
            if self._absent[driver] >= CLOSE_AFTER_CLEAN_FRAMES:
                done = self._close(driver)
                if done is not None:
                    closed.append(done)
        return closed + self._close_stale(now)

    def _own_driver(self, ids: dict, board) -> int | None:
        own_y = (board[1] + board[3]) // 2
        near = [y for y in ids if abs(y - own_y) <= ROW_MATCH_TOL]
        return ids[near[0]] if near else None

    def _neighbour(self, ids: dict, own_place: int | None, step: int):
        """The driver one place ahead of or behind us, or `None`.

        `None` rather than a guess: a gap whose owner is unknown must not be
        folded into a trend that thinks it knows.
        """
        if own_place is None:
            return None
        wanted = own_place + step
        for driver, place in self._position.items():
            if place == wanted:
                return driver
        return None

    def _close_stale(self, now: float) -> list:
        """Close visits nobody has seen either way for a long time.

        A car can leave the visible top eight while it is standing, and then
        neither the board nor its absence says anything about it ever again.
        Without a clock that visit stays open to the flag.
        """
        closed = []
        for driver, visit in list(self._visits.items()):
            last = visit.last_s or visit.started_s
            if now - last >= CLOSE_AFTER_SILENT_S:
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
        # **A cluster too rarely seen to be a driver cannot file a stop.**
        # Same run-length argument `Roster.drivers` makes: a real driver is on
        # the board through the race, a misread appears once or twice. Without
        # this the Spa race filed twelve stops for eight drivers, the extra
        # four being two-reading fragments that had founded clusters of their
        # own - and each took a driver handle with it, so the book would have
        # carried four people who never existed into the next race.
        if self._roster.sightings(driver) < MIN_SIGHTINGS:
            _log.info("pit-wall: a stop from a cluster seen only %d times is "
                      "not filed - that is a misread, not a driver",
                      self._roster.sightings(driver))
            return None
        watched = max(0.0, visit.last_s - visit.started_s)
        if watched < MIN_WATCHED_S:
            _log.info("pit-wall: %s discarded - %d reads over %.0f s is too "
                      "brief to be a stop", self._roster.name_of(driver)
                      or f"driver {driver}", len(visit.readings), watched)
            return None
        name = self._roster.name_of(driver)
        if not name and self._name_for is not None:
            # **A handle already in use is not a handle.** `name_for` reads the
            # archive, so two clusters named before either has been written
            # back both come out as "Car #1" and the whole field collapses onto
            # one driver. Run over a real race that filed thirteen stops
            # against a single name. The roster knows what it has issued, so
            # ask again until the answer is new.
            taken = {self._roster.name_of(other)
                     for other in self._roster.drivers()
                     if self._roster.name_of(other)}
            try:
                candidate = self._name_for(taken)
            except TypeError:
                # A namer that does not want the set is still welcome.
                candidate = self._name_for()
            except Exception:               # pragma: no cover - belt
                _log.exception("pit-wall: could not name a driver")
                candidate = None
            if candidate and candidate not in taken:
                name = candidate
                self._roster.label(driver, name)
        # **A fill that did not move was not watched, whatever else happened.**
        # `partial` means the entry figure is an upper bound rather than a
        # measurement, and a visit whose lowest and highest readings are the
        # same number is the strongest possible case of that: nothing was seen
        # to change. Measured on the Spa race, one driver came back 19 L in and
        # 19 L out on two readings - a fragment of a stop that really ran to
        # 83 L. Filed, because he did stop and that is a fact worth keeping,
        # but kept out of anything that computes a rate.
        stop = visit.as_stop()
        no_fill = (stop.litres is not None and stop.litres <= 0)
        seen = Seen(driver=name, driver_id=driver,
                    stop=stop, reads=len(visit.readings),
                    compound_reads=len(visit.compounds),
                    watched_s=watched, partial=visit.partial or no_fill)
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
