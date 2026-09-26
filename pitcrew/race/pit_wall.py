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
from pitcrew.race.gap_signal import GapSample
from pitcrew.race.gaps import GapTrend, read_gaps
from pitcrew.race.rivals import Stop
from pitcrew.telemetry.board import flag_ladder, own_row
from pitcrew.telemetry.compound import read as read_compound
from pitcrew.telemetry.hud_digits import read_fuel
from pitcrew.telemetry.pit_columns import read_rows
from pitcrew.telemetry.roster import ROW_MATCH_TOL, Roster, is_own_row
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

# ...and for at least this long. **A frame count is not a duration, and the
# grab rate is his to change.** Three frames was tuned at the 2 s grab this ran
# at - about 4 to 6 s of a car visibly out of his box. At the 0.5 s grab he
# moved to on 19 Sep 2026 (so the disc's flip at the lane exit is caught) the
# same three frames are 1.5 s, and a pit crew washing a disc out behind the
# translucent HUD for under two seconds would close a stop in the middle of
# its fill. Both have to hold: the frames stop one bad read closing a visit,
# the seconds stop a fast grab doing it three times in a second and a half.
# 4.0 is what three frames span at 2 s, so behaviour at the old rate is
# exactly what it was.
CLOSE_AFTER_CLEAN_S = 4.0

# **How long a board place stays true after its row was last read.** A car
# near enough to race - `rival_calls.NEARBY_PLACES` either side - sits on the
# visible board every frame, so a place not re-read in this long belongs to a
# car that has left the rows around us, and the place it last held says
# nothing about which side of us he is now (critic, 19 Sep: "Attack." or
# "Keep fighting." was chosen off a place that never expired).
POSITION_FRESH_S = 30.0

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

# **GT7's tank is 100 L for almost every car (CLAUDE.md §3.4).** A fuel
# reading above this limit is a misread (AV1 compression can produce digit
# artefacts like 261 L, 351 L). Refuse any reading above this cap and log it.
# (Issue 7, 26 Sep 2026 coordinator replay review.)
FUEL_CAPACITY_MAX_L = 100

# Sub-threshold visit fragments are kept for this long after they closed.
# When two fragments' clusters later merge (via OCR identity), the combined
# readings are re-evaluated against the stop bar. 180 s matches the silence
# timeout: a car that stopped and dropped off the board is re-found within
# one lap, and an OCR resolution fires within seconds to minutes of the
# capture.  (Fault 3, coordinator 26 Sep 2026.)
FRAGMENT_TTL_S = 180.0

# P3-2 (26 Sep 2026): maximum time gap in seconds between two fragments'
# observation windows before they are considered TOO FAR APART to be the same
# stop.  Matches db._FOLD_MAX_GAP_S — GT7's measured dead time before the
# hose connects is ~16.9 s (rivals.DEAD_TIME_S), so 20 s is the minimum
# separation that two genuinely different visits can have.  Two fragments more
# than 20 s apart in wall-clock time cannot be the same pit stop.
STOP_COMBINE_MAX_GAP_S = 20.0

# P3-4 (26 Sep 2026): when a 1-read fragment is combined into another visit,
# the single fuel reading must not be more than this many litres BELOW the
# other visit's minimum reading.  A garbage OCR digit (e.g. 3 L on a car
# filling from 40 L) would be far below the range; this tolerance allows for
# minor read noise on the same fill.  Upper-bound check is strict (≤ exit):
# a reading above the other visit's highest seen level is inconsistent with
# having been taken during the same fill phase.
_FRAGMENT_FUEL_TOLERANCE_L = 5

# A driver must be seen this many times before he is a driver rather than a
# misread. See `Roster.drivers`.
MIN_SIGHTINGS = 20

# **A tyre read must come from THIS visit's own disc** - same x, same size,
# within this many pixels. On Sardegna Rd 9 every one of 1,681 real discs sat
# at x 290-294 (rivals) or 373-377 (ours), 26-29 by 27-30 px, and none of 96
# scenery "discs" that reached a pit row matched both (critic, 19 Sep 2026).
# The disc a visit is held to is the one on its first frame whose FUEL read.
DISC_ANCHOR_PX = 2

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
    # `(x0, width, height)` of this visit's disc, fixed on the first frame
    # whose fuel read - see `DISC_ANCHOR_PX`. No compound is counted before.
    disc_at: tuple | None = None
    # The fuel read on the frame of the LAST compound read, and when it was
    # taken - what `left_on` checks a flip against.
    last_compound_l: int | None = None
    last_compound_s: float | None = None
    # Set by `_close` only when his row came back WITHOUT columns - the one
    # close whose last frame is the lane exit, where the disc flips.
    closed_on_absence: bool = False
    # **The car dropped out of the visible rows before MIN_READS or
    # MIN_WATCHED_S was met.** We know he stopped (pit columns were seen and
    # a fuel figure was read), but we could not read the fill. Fuel out is
    # unknown - set to None in `_close` rather than using `max(readings)`.
    left_view: bool = False

    @property
    def entry_l(self) -> int | None:
        return min(self.readings) if self.readings else None

    @property
    def exit_l(self) -> int | None:
        return max(self.readings) if self.readings else None

    @property
    def rising_when_last_read(self) -> bool:
        """Whether the last two readings were still going UP.

        **Evidence for the log, NOT a reason to hold a visit open.** It was
        briefly used as one - "a tank still filling belongs to a car still
        standing" - and the pit-wall tests rejected it correctly: once a car
        LEAVES, readings stop arriving, so a fill that rose to 83 L and drove
        off reads as rising forever. From the readings alone a departed car
        and a standing one with an unreadable disc are indistinguishable, and
        the rule held every stop open to the 180 s timer.

        What does tell them apart is the white "P" flag beside the position:
        measured on Sardegna Rd 9 at 0.87-0.88 bright on every pit row and
        0.00 on most others - but scenery also read 0.27, 0.44 and 0.71 on
        it, so it needs a shape test and calibration before it can decide a
        close. Until then this only COUNTS how often the absence rule cuts a
        fill that was still rising, which is the number that calibration
        needs.
        """
        return (len(self.readings) >= 2
                and self.readings[-1] > self.readings[-2])

    @property
    def compound(self) -> str | None:
        """The tyre he LEFT on - our best reading of it - or `None`.

        **The disc on GT7's timing totem changes only as the car exits the
        pit lane** (the driver, 19 Sep 2026). While he stands it shows the
        tyres he ARRIVED on, whatever the crew fits. So the vote across the
        stop - `arrived_on` - is the stint he just FINISHED, and the tyre he
        leaves on is the LAST read, taken as he goes.

        This used to file the vote, so every car that changed compound was
        filed with the tyres it came in on. It matched our own stop at
        Sardegna Rd 9 exactly: we fitted RH and the disc read M from entry to
        the last frame watched.

        Where the last read differs from the vote, the change was SEEN and
        this is the tyre he left on. Where it does not, he either refitted
        the same compound or the flip landed between two grabs; this returns
        the arrival compound as the best estimate and `compound_changed` is
        None, so nothing downstream reads "same tyre" as a fact.
        """
        arrived = self.arrived_on
        left = self.left_on
        if left is not None and arrived is not None and left != arrived:
            return left
        return arrived

    @property
    def left_on(self) -> str | None:
        """The compound read as he left the lane, or `None`.

        **One frame by the nature of the signal**, so there is no vote here:
        the disc flips as the car exits and is on screen for 0.25-0.35 s
        (measured at 60 fps, Sardegna Rd 9) - one 0.5 s grab at most. The
        reader alone cannot stand behind one frame: its glyph bank holds only
        "S", so M, H, W and I are colour alone, and 197 of 211 scenery reads
        on that race came back H. So a single read is the tyre he left on
        only where all of this holds (critic, 19 Sep 2026):

        * it came from this visit's own disc (`DISC_ANCHOR_PX`, at the read);
        * it is the TAIL - taken on the last frame his columns were seen;
        * the visit closed on ABSENCE, his row back without columns. A visit
          closed on the silence clock or at the flag ended mid-stand, and its
          last read is the arrival disc, not the flip;
        * where the fuel read on that frame, it is the fill's final figure -
          a flip mid-fill is not the exit.

        Anything short of that is `None`: "no change seen", which is never
        "no change".
        """
        if not self.compounds or not self.closed_on_absence:
            return None
        if self.last_compound_s is None or self.last_compound_s != self.last_s:
            return None
        if (self.last_compound_l is not None
                and self.last_compound_l != self.exit_l):
            return None
        return self.compounds[-1]

    @property
    def compound_changed(self) -> bool | None:
        """True where the disc was SEEN to change as he left. None otherwise -
        a refit of the same set and a flip the grab missed look identical."""
        arrived, left = self.arrived_on, self.left_on
        if arrived is not None and left is not None and left != arrived:
            return True
        return None

    @property
    def arrived_on(self) -> str | None:
        """The letter agreed on across this stop - the tyres he came IN on.

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
                    compound_in=self.arrived_on,
                    # **Set for a rival at last.** `tyres_changed` has existed
                    # on `Stop` and been None for every rival ever filed; a
                    # compound change seen at the lane exit PROVES it. No
                    # change seen proves nothing - a same-compound refit is
                    # invisible on the disc - so that stays None (rule 3).
                    tyres_changed=True if self.compound_changed else None,
                    fuel_in_l=(float(self.entry_l)
                               if self.entry_l is not None else None),
                    fuel_out_l=(float(self.exit_l)
                                if self.exit_l is not None else None))


@dataclass(frozen=True)
class Entered:
    """A car seen standing in its box, while it is still standing there.

    `fuel_in_l` is what it arrived with - the LOWEST reading so far, because a
    fill only goes up. `None` where no digit could be transcribed, which is a
    refusal and not an empty tank.
    """
    driver: str | None
    driver_id: int
    lap: int | None
    fuel_in_l: int | None
    partial: bool
    # **Whether he was ahead of us when he went in**, off the last board
    # read that showed him OUT of the lane, against our own place on that
    # same read. `None` where either place was unread. A car ahead that pits
    # drops behind us on the position byte without being passed - Bathurst
    # lap 11, "You've made 2 places" about two cars standing in their boxes.
    ahead_at_entry: bool | None = None


@dataclass(frozen=True)
class OwnFill:
    """OUR stop, off the pit columns, on a path of its own.

    **Refusing to file his stop as a rival's left nothing filing it as his.**
    `_close` has two own-car branches and both returned `None`, so every
    reading taken off his own row was dropped on the floor: Bathurst, 20 Sep
    2026, the fill was on screen for both of his stops and read for everybody
    but him (`logs/pitcrew.log:6632`, `:9918`). The refusal is right - a stop
    filed into `rival_stops` under his own name feeds his habits back to him
    as an opponent's - and it is a refusal to file it *there*, not a reason to
    lose it.

    So this is deliberately NOT a `Seen`, and it never reaches `on_stop`:
    nothing that files rivals can be handed one by mistake. It carries the
    same evidence a rival's stop does (rule 4), and every figure on it may be
    `None`, which means the screen could not be read and never that the tank
    was empty (rule 3).

    `standing` is True while the columns are still on our row - the live view,
    where `fuel_out_l` is the latest reading rather than the last one, and
    `litres` is what has gone in so far.
    """
    driver_id: int
    stop: Stop
    reads: int
    compound_reads: int
    # None where the two stamps disagree about which came first - rule 3 and
    # rule 9: how long the fill was watched is then not known, and is not 0.
    watched_s: float | None
    partial: bool
    # He is still in the box, as far as the wall can see. The figures are a
    # fill in progress, not a finished one.
    standing: bool = False
    # As on `Seen`: closed by the clock rather than by seeing him leave, so
    # `fuel_out_l` is a lower bound on the fill and not the fill.
    exit_is_a_bound: bool = False

    @property
    def lap(self) -> int | None:
        return self.stop.lap

    @property
    def fuel_in_l(self) -> float | None:
        return self.stop.fuel_in_l

    @property
    def fuel_out_l(self) -> float | None:
        return self.stop.fuel_out_l

    @property
    def litres(self) -> float | None:
        """Fuel taken. `None` rather than a clamp - see `Stop.litres`."""
        return self.stop.litres


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
    # **The car left the board before anyone saw it leave the box.** `exit_l`
    # is `max(readings)`, so a visit closed by the stale timer rather than by
    # seeing the car back on track has an exit figure that is a LOWER BOUND -
    # a reading from the middle of the fill. Measured example: a driver
    # filling 10 -> 89 L who drops below the visible top eight at 40 s files
    # as ~50 L, and 50 L looks exactly like a car that chose to underfill.
    # `partial` does not cover this: it means the entry figure is an upper
    # bound, which is the opposite end of the same stop.
    exit_is_a_bound: bool = False
    # **The car left the visible rows before MIN_READS or MIN_WATCHED_S was
    # reached** (brief_names_stops.md part B). We know the stop happened (pit
    # columns were seen, ≥1 fuel reading was taken, the identity is known) but
    # the fill was not watched. `stop.fuel_out_l` is `None` - the exit figure
    # is unknown, not `max(readings)`. Rule 3: a bound dressed as a reading.
    left_view: bool = False
    # Monotonic clock seconds bounding the observation window: when the first
    # frame of this visit was seen and when the last read was taken.  Passed
    # through to record_rival_stop so the duplicate-fold guard can use time
    # overlap rather than lap ±1 alone (P3-1, 26 Sep 2026).  None when the
    # Seen was not built from a Visit (e.g. tests that construct it directly).
    visit_start_s: float | None = None
    visit_end_s: float | None = None


class PitWall:
    """Who is on the board, who is in the lane, and what their stop cost.

    Built once per session and reset between them. CLAUDE.md rule 11: the
    roster, the visits and the positions all describe one race, and a race that
    opens holding the last one's is a race that reports it.
    """

    def __init__(self, roster: Roster | None = None, *, on_stop=None,
                 on_enter=None, min_sightings: int = MIN_SIGHTINGS,
                 name_for=None, where_on_lap=None, on_gap=None,
                 on_board=None, on_own_fill=None,
                 ocr_namer=None,
                 on_board_reads=None,
                 on_ocr_rename=None) -> None:
        self._roster = roster if roster is not None else Roster()
        # **How many identities it opened with, against how many cars are out
        # there.** Bathurst, 20 Sep 2026: `seeded with 160 known drivers` for
        # a seven-car race (`logs/pitcrew.log:3233`), while the app itself was
        # saying "P3 of 7" out loud all evening off `packet.cars_in_race`.
        # Two numbers that were both known, in two different places, and
        # nothing ever put them side by side. Counted and reported only - a
        # cap on founding is a behaviour change and is not this.
        self._seeded = len(self._roster)
        self._field_size: int | None = None
        self._said_the_field = False
        self._on_stop = on_stop
        # **Our own fill, which `on_stop` must never carry.** See `OwnFill`:
        # the branch that refuses to file his stop as a rival's is right, and
        # it left nothing filing it as his. Fired once per own stop, at the
        # close, with the same evidence a rival's stop carries.
        self._on_own_fill = on_own_fill
        # **Entering is a different event from having stopped, and it is the
        # one the driver can still act on.** `on_stop` fires when the car
        # LEAVES, which for `rival_boxed` - "he has boxed on 12 litres, that is
        # about forty seconds standing" - is a minute too late to be worth
        # saying. Fired once per visit, on the reading that confirms it.
        self._on_enter = on_enter
        self._announced: set[int] = set()
        self._own: int | None = None
        # **How many sightings make a cluster a driver**, injectable so a test
        # can reach it without feeding twenty full frames per case. Twenty
        # board reads a test cost three minutes across this file.
        self._min_sightings = min_sightings
        # **OCR namer**, optional. When provided, native pixel crops are
        # buffered per cluster and OCR is run off the capture thread to name
        # drivers the exemplar bank has never seen. Part A, 26 Sep 2026.
        # Callbacks are set here so the namer can call back into the wall.
        self._ocr_namer = ocr_namer
        if ocr_namer is not None:
            ocr_namer.on_named = self._ocr_named
            ocr_namer.on_merge = self._ocr_merge
            ocr_namer.on_rename = self._ocr_rename
        # **Session-scoped DB rename callback** (CRITICAL 1, 26 Sep 2026).
        # Fired from `_ocr_rename` so the controller can rename this
        # session's rival_stops rows only.  Past sessions must not be
        # touched by a live OCR event.
        self._on_ocr_rename = on_ocr_rename
        # **Asked for a name at the moment a stop closes, not at the flag.** A
        # stop closes DURING the race, and whatever files it refuses a stop
        # with no driver on it - so a cluster the archive did not recognise had
        # its stop dropped, and naming the field afterwards was hours too late
        # for a fact that cannot be observed twice. `name_for()` returns a
        # provisional handle; the driver turns it into a person later, and
        # renaming carries the stops with it.
        self._name_for = name_for
        # **Where on the road this frame was taken.** A callable, because it is
        # asked at the moment the grab returns rather than at the moment the
        # wall was built. Without it a gap cannot be binned into sectors later
        # and the position cannot be recovered - the frame is gone and so is
        # the packet. See `race/lap_ruler.py`.
        self._where_on_lap = where_on_lap
        # **Each reading as it is taken, and each frame's rows** (D7, 14 Sep
        # 2026). The trends and `positions()` reach the race once a lap, at
        # the crossing; George now volunteers the gap and a rival's place
        # mid-lap, and a lap-old gap said as "2.1" is a figure from a minute
        # ago. `on_gap(side, gap_s, driver_id, name)` per reading;
        # `on_board(rows, own_row)` per frame with our own row identified,
        # `rows` as `(row, name or None)` for THIS frame only - never the
        # sticky `_position`, which keeps a car's last row after it has gone.
        # Worker thread, guarded: a hook that raises costs its own reading.
        self._on_gap = on_gap
        self._on_board = on_board
        # **Batch of rich row data for the board_reads table.** Fired once per
        # frame from `_see()` with a list of dicts carrying at_s, lap, position,
        # cluster_id, name, name_source, pit_columns, fuel_l and compound.  The
        # controller writes these to the DB off the capture thread.
        self._on_board_reads = on_board_reads
        self._visits: dict[int, Visit] = {}
        self._absent: dict[int, int] = {}
        # When each driver's current run of absent frames began - see
        # `CLOSE_AFTER_CLEAN_S`.
        self._absent_since: dict[int, float] = {}
        # Drivers seen on the board WITHOUT pit columns. A visit that begins
        # for a driver who is not in here started after the fill did, so far as
        # anything can tell - which is what `partial` means.
        self._seen_clean: set[int] = set()
        # `driver -> (his place, our place)` on the last board read that
        # showed him out of the lane. What `Entered.ahead_at_entry` is from.
        self._clean_place: dict[int, tuple[int, int | None]] = {}
        self._position: dict[int, int] = {}
        # When each `_position` was last read - see `POSITION_FRESH_S`.
        self._position_at: dict[int, float] = {}
        # The screen row each driver was last read on - see the absence rule.
        self._row_y: dict[int, int] = {}
        self._pitted: set[int] = set()
        self._stops: list[Seen] = []
        # Sub-threshold visit fragments (≥1 fuel read but below MIN_READS or
        # MIN_WATCHED_S). Keyed by cluster id. Kept for FRAGMENT_TTL_S so that
        # when two clusters later merge via OCR identity the combined readings
        # can be re-evaluated against the stop bar.  (Fault 3, coordinator
        # 26 Sep 2026.)
        self._fragments: dict[int, tuple[float, "Visit"]] = {}
        # Our own stops, kept apart from `_stops` so that nothing which walks
        # the rivals can pick one up. See `OwnFill`.
        self._own_fills: list[OwnFill] = []
        # The two intervals GT7 publishes either side of us, per lap. Kept as
        # trends rather than instants because a closing RATE is the cheapest
        # pace signal on the screen - see `race/gaps.py`.
        self.ahead = GapTrend(side="ahead")
        self.behind = GapTrend(side="behind")
        # Every gap reading with the road position it was taken at, which is
        # what `race/sectors.py` bins. Kept raw here; the conditioning lives in
        # `race/gap_signal.py`.
        self.samples: list[GapSample] = []
        self._frames = 0
        self._clean = 0
        # **Every stage that can silently return nothing gets a counter.**
        # The wall watched a whole race on 4 Sep 2026, took 843 frames and
        # logged not one line - no board, no driver, no gap, no stop, and no
        # error either - so "the board was read and nobody pitted" and "the
        # board was never found" were the same silence. Counting separates
        # them, and the counters must be REPORTED: see `health()`.
        # CLAUDE.md rule 10 - log the accepts, not only the refusals.
        # **Every counter is FRAMES, so the line reads as one funnel.** A
        # first version counted `named` once per driver per frame and
        # `pit_cols` once per pit row per frame, so a healthy race printed
        # 843 -> 800 -> 790 -> 790 -> 5800 -> 700 -> 40 and read as a bug.
        self._stage = {"ladder": 0, "own_row": 0, "rows": 0, "named": 0,
                       "gaps": 0, "pit_cols": 0, "own_driver": 0, "fuel_read": 0,
                       # A visit the absence rule closed while its tank was
                       # still rising - see `Visit.rising_when_last_read`.
                       "closed_mid_rise": 0,
                       # A tyre read on his row from a disc that is not his
                       # visit's own - scenery, see `DISC_ANCHOR_PX`.
                       "disc_off_anchor": 0,
                       # **The same two questions asked of OUR row alone.**
                       # Bathurst, 20 Sep 2026: his lap-11 stop logged "0 fuel
                       # reads over 17 s" while rivals in the same window took
                       # 20 to 60 each, and his lap-21 stop read enough to
                       # clear the bar - so the own row is sometimes readable
                       # and sometimes not, and nothing in the log could say
                       # how often. Our own row is the white plate, which is
                       # what the white-disc and bright-ink tests find easiest
                       # to see, so a column found on it is not yet a figure
                       # read off it. `own_pit_cols` is FRAMES, `own_fuel_read`
                       # is readings - the two numbers the next race needs to
                       # answer whether his row is genuinely harder.
                       "own_pit_cols": 0, "own_fuel_read": 0}

    # --- lifecycle ------------------------------------------------------

    def _name_or_mint(self, driver: int) -> str | None:
        """His name, minting a handle if the roster has none.

        **Extracted so the ENTRY can name a car too.** It was only done at
        `_close`, so a driver the archive had never seen was nameless while he
        stood in the box - and the entry call, which refuses a nameless car,
        was refused for every driver in a field the app has not met. With zero
        rows in `drivers` that is every driver, in every race, so the call
        ranked above every other rival call could not be spoken once.

        **A handle already in use is not a handle.** `name_for` reads the
        archive, so two clusters named before either has been written back both
        come out as "Car #1" and the whole field collapses onto one driver. Run
        over a real race that filed thirteen stops against a single name. The
        roster knows what it has issued, so ask again until the answer is new.
        """
        name = self._roster.name_of(driver)
        if name or self._name_for is None:
            return name
        taken = {self._roster.name_of(other)
                 for other in self._roster.drivers()
                 if self._roster.name_of(other)}
        try:
            candidate = self._name_for(taken)
        except TypeError:
            # A namer that does not want the set is still welcome.
            candidate = self._name_for()
        except Exception:                   # pragma: no cover - belt
            _log.exception("pit-wall: could not name a driver")
            candidate = None
        if candidate and candidate not in taken:
            self._roster.label(driver, candidate)
            return candidate
        return None

    def _announce_entry(self, driver: int, visit, lap, own: int | None) -> None:
        """Say he is in, once per VISIT, as soon as the reading is credible.

        Four gates, and each of them was a defect:

        * **Only once the visit has met the bar a STOP is filed on** -
          `MIN_READS` fuel readings over `MIN_WATCHED_S` - not on the second
          reading. Bathurst, 14 Sep 2026: Car #30 was announced on its second
          reading at 20:39:32 and discarded by `_close` three minutes later as
          "4 reads over 13 s is too brief to be a stop". A stop that is not
          filed must not have been said. The price is latency: the fifteen
          seconds of the bar, against filed visits that night of 16 to 84 s
          watched and a GT7 stop of 50-100 s standing - so he is still in
          the box when it is said. It is the same function `_close` uses for
          our own car, so the two bars cannot drift.
        * **Not before the second reading either**, which the bar above
          includes: one frame can catch a marshal walking across the row, and
          "he has boxed" cannot be un-heard.
        * **Not our own car.** `read_rows` is the one path that returns the
          driver's own row, so without this the app announces our own stop and
          then compares it against itself.
        * **Not a cluster too rarely seen to be a driver.** `_close` refuses
          one below `MIN_SIGHTINGS` as a misread; announcing it aloud first and
          then declining to file it is the weaker bar on the louder channel.
        """
        if (self._on_enter is None or driver in self._announced
                or not self._is_a_stop(visit)
                or (own is not None and driver == own)
                or self._roster.spaced_sightings(driver)
                < self._min_sightings):
            return
        name = self._name_or_mint(driver)
        if not name:
            # **Refusing must not consume the one chance.** Added to
            # `_announced` before the name was resolved, a nameless first
            # attempt spent the announcement and no later frame could recover
            # it - a refusal that becomes its own baseline (rule 10).
            return
        self._announced.add(driver)
        clean = self._clean_place.get(driver)
        ahead = (clean[0] < clean[1]
                 if clean is not None and clean[1] is not None else None)
        # Rule 10: the accept is logged, with the evidence that passed.
        _log.info("pit-wall: %s confirmed in the lane - %d reads over %.0f s, "
                  "in on %s L%s, %s us when he went in", name,
                  len(visit.readings), visit.last_s - visit.started_s,
                  visit.entry_l, " (joined mid-fill)" if visit.partial else "",
                  {True: "ahead of", False: "behind", None: "unplaced against"}
                  [ahead])
        try:
            self._on_enter(Entered(driver=name, driver_id=driver,
                                   lap=visit.lap if visit.lap is not None
                                   else lap,
                                   fuel_in_l=visit.entry_l,
                                   partial=visit.partial,
                                   ahead_at_entry=ahead))
        except Exception:                                    # pragma: no cover
            _log.exception("pit-wall: the entry hook raised")

    def take_samples(self) -> list[GapSample]:
        """Every gap reading since the last take, and the list is cleared.

        Drained on our crossing by the controller, which files them and
        hands the lap's samples to the sector map. **Taken and cleared in
        one**, so a lap's readings are never folded in twice. Worker thread
        appends and the Qt thread takes; the swap is a single rebinding.
        """
        taken, self.samples = self.samples, []
        return taken

    def new_session(self) -> None:
        """Forget the last race. Everything here is about one of them.

        The roster is kept: driver identities are the one thing that SHOULD
        cross a session boundary, and it is seeded from the archive anyway.
        """
        self._visits.clear()
        self._absent.clear()
        self._absent_since.clear()
        self._seen_clean.clear()
        self._clean_place.clear()
        self._position.clear()
        self._position_at.clear()
        self._row_y.clear()
        self._pitted.clear()
        # **Or every driver's entry is announced once per APP RUN.** Rule 11:
        # anything cached across a session boundary needs an explicit reset,
        # and this one silences the call for the whole of the second race.
        self._announced.clear()
        self._own = None
        self._stops = []
        self._fragments.clear()
        # Rule 11: last race's fill is not this race's, and a stale one read
        # live is read as "he has just taken 40 litres".
        self._own_fills = []
        # **And the field, for the same reason the entry call above is.**
        # `_said_the_field` is a one-shot, so without this the first session
        # of the run consumes it and every later race's health line carries
        # the PREVIOUS race's field size - a 7-car Supercars grid printed
        # against a 20-car GT3 one, which is the comparison the line exists
        # to make.
        self._said_the_field = False
        self._field_size = None
        self.ahead.new_session()
        self.behind.new_session()
        self.samples = []
        self._frames = self._clean = 0
        for key in self._stage:
            self._stage[key] = 0
        if self._ocr_namer is not None:
            self._ocr_namer.new_session()

    @property
    def roster(self) -> Roster:
        return self._roster

    @property
    def own_cluster_id(self) -> int | None:
        """The cluster id for the driver's own car row, or None if not seen.

        Used by the controller to skip minting the own car as a phantom handle.
        """
        return self._own

    def stops(self) -> list[Seen]:
        return list(self._stops)

    def own_fills(self) -> list[OwnFill]:
        """Our own stops this session, oldest first. Never rivals'."""
        return list(self._own_fills)

    def own_fill(self) -> OwnFill | None:
        """His fill: the one happening now, else the last one finished.

        **The live one only once it has met the bar a stop is filed on** -
        `_is_a_stop`, the same two bars `_close` and `_announce_entry` use, so
        the three cannot drift. A glimpse is not a stop, ours any more than a
        rival's, and a figure on a screen that says he is filling when he is
        driving past the pit entry is the same error as saying it aloud.

        `standing` is True on the live one, and its `fuel_out_l` is the
        latest reading rather than the last - so `litres` is what has gone in
        so far. `None` where nothing has been watched at all.
        """
        visit = self._visits.get(self._own) if self._own is not None else None
        if visit is not None and self._is_a_stop(visit):
            return self._own_fill_from(visit, standing=True)
        return self._own_fills[-1] if self._own_fills else None

    @staticmethod
    def _own_fill_from(visit, *, standing: bool = False,
                       exit_is_a_bound: bool = False) -> OwnFill:
        return OwnFill(driver_id=visit.driver, stop=visit.as_stop(),
                       reads=len(visit.readings),
                       compound_reads=(1 if visit.compound_changed
                                       else len(visit.compounds)),
                       # **Not `max(0.0, ...)` - rule 9.** Both stamps come
                       # off one monotonic clock so this cannot go negative
                       # today, and that is exactly why the clamp was free to
                       # write and worthless: the day the clock does fault, a
                       # clamp reports "watched for 0 s" - a well-formed
                       # reading nothing downstream can tell from a real one -
                       # where None says the duration is not known.
                       watched_s=(None if visit.last_s < visit.started_s
                                  else visit.last_s - visit.started_s),
                       partial=visit.partial, standing=standing,
                       exit_is_a_bound=exit_is_a_bound)

    def positions(self, *, max_age_s: float | None = None,
                  now: float | None = None) -> dict[str, int]:
        """Board position per named driver, best effort.

        `max_age_s` leaves out a place not re-read in that long - the race
        asks with `POSITION_FRESH_S`. Without it every place ever read is
        returned, which is what the per-lap archive files.

        **Snapshotted before it is walked.** `_position` is written on the
        sampler's worker thread and read on the Qt one, so iterating it live
        raises `RuntimeError: dictionary changed size during iteration` if a
        driver is added mid-walk. The caller's blanket `except` would swallow
        that into a championship call that intermittently and silently does not
        happen - the worst kind of failure, because nothing says it failed.
        """
        out = {}
        clock = time.monotonic() if now is None else now
        read_at = dict(self._position_at)
        for driver, place in list(self._position.items()):
            if max_age_s is not None and clock - read_at.get(
                    driver, float("-inf")) > max_age_s:
                continue
            name = self._roster.name_of(driver)
            if name:
                out[name] = place
        return out

    def note_field_size(self, cars: int | None) -> None:
        """How many cars are actually in this race, from the packet.

        Said once, the first time a real figure arrives, against the number of
        identities the roster was seeded with - because the mismatch is the
        thing nobody could see: 160 candidates for a 7-car field, every one of
        them a cluster a row could be matched to or split against.

        **A reading, not a rule.** Nothing here refuses or caps anything on
        it; it is on the health line so the next race can be read.
        """
        if not cars or cars <= 0:
            return                       # 0 is "no reading", never a field
        self._field_size = int(cars)
        if self._said_the_field:
            return
        self._said_the_field = True
        _log.info("pit-wall: seeded with %d known driver%s for a field of %d, "
                  "and holding %d identit%s now", self._seeded,
                  "" if self._seeded == 1 else "s", self._field_size,
                  len(self._roster),
                  "y" if len(self._roster) == 1 else "ies")

    def has_pitted(self, driver_id: int) -> bool:
        """Whether this car has been seen in the lane THIS session.

        A latch, not a reading: the columns are gone the moment he leaves, so
        asking the screen later answers a different question.
        """
        return driver_id in self._pitted

    # --- the frame ------------------------------------------------------

    def where(self) -> float | None:
        """Metres round the lap, or `None` where the ruler cannot say."""
        if self._where_on_lap is None:
            return None
        try:
            return self._where_on_lap()
        except Exception:               # pragma: no cover - belt
            return None

    def health(self) -> str:
        """One line saying how far up the pipeline each frame got.

        **The wall's silence used to be indistinguishable from its absence.**
        On 4 Sep 2026 it watched a whole 20-lap race, was handed 843 frames,
        and wrote nothing to the log at all - because it only ever logs when it
        FINDS a stop. Afterwards there was no way to tell whether the board had
        been read and nobody had pitted, or whether the board had never been
        found. Each stage below can return nothing without raising, so each is
        counted, and the first one reading 0 is the one to fix.
        """
        s = self._stage
        # **The roster's accepts beside its refusals** (rule 10): rows that
        # joined a driver, rows that founded one, and rows refused the driver
        # a closer row of the same frame held. Cumulative for the roster.
        counts = getattr(self._roster, "counts", None) or {}
        return ("pit-wall: %d frames -> ladder %d -> own row %d -> rows %d "
                "-> any named %d -> our row %d -> gaps %d -> pit columns %d "
                "-> fuel read %d | %d driver%s placed, %d stop%s filed, "
                "%d closed mid-rise, %d off-disc tyre read%s | "
                "our own row: pit columns on %d frames -> fuel read %d, "
                "%d own fill%s kept | seeded %d for a field of %s, "
                "holding %d | "
                # **`merged` beside the rest** (rule 10, and B#7): a cluster
                # folded into another was neither counted nor logged, so a
                # race that split seven cars into twenty-seven identities
                # could not say whether the merge path had run at all.
                "roster rows matched %d, founded %d, contested %d, merged %d"
                % (
                    self._frames, s["ladder"], s["own_row"], s["rows"],
                    s["named"], s["own_driver"], s["gaps"], s["pit_cols"],
                    s["fuel_read"],
                    len(self._position), "" if len(self._position) == 1 else "s",
                    len(self._stops), "" if len(self._stops) == 1 else "s",
                    s["closed_mid_rise"], s["disc_off_anchor"],
                    "" if s["disc_off_anchor"] == 1 else "s",
                    s["own_pit_cols"], s["own_fuel_read"],
                    len(self._own_fills),
                    "" if len(self._own_fills) == 1 else "s",
                    self._seeded,
                    "unknown" if self._field_size is None
                    else self._field_size, len(self._roster),
                    counts.get("matched", 0), counts.get("founded", 0),
                    counts.get("contested", 0), counts.get("merged", 0)))

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
        self._stage["ladder"] += 1
        # **The ladder we already have, not a second search.** `own_row` finds
        # one itself when it is not given one, and this runs on the sampler's
        # worker thread where a duplicated O(n^2) scan over every saturated run
        # in a 1920x1080 frame comes straight out of the wear gauge's budget.
        board = own_row(frame, ladder=ladder)
        if board is None:
            return self._close_stale(now)
        self._stage["own_row"] += 1
        rows = read_rows_of_board(frame, board, ladder)
        if not rows:
            return []
        self._stage["rows"] += 1
        self._clean += 1
        ids: dict[int, int] = {}
        identified: set[int] = set()
        frame_rows: list[tuple[int, int | None]] = []
        # **The whole board at once**, so no two rows of one frame can come
        # back as one driver - see `Roster.see_frame`.
        resolved = self._roster.see_frame([row.name for row in rows],
                                          now=now)
        own_row_place = next((place for place, row in enumerate(rows, start=1)
                              if row.is_own), None)
        unread_ys: list[int] = []
        for place, (row, driver) in enumerate(zip(rows, resolved), start=1):
            frame_rows.append((place, driver))
            if driver is None:
                unread_ys.append(row.y)
                continue
            ids[row.y] = driver
            self._row_y[driver] = row.y
            identified.add(driver)
            self._position[driver] = place
            self._position_at[driver] = now
            # **Feed native crops to the OCR namer**, off the capture thread.
            # Only rows with a native crop and a bitmap are worth OCR-ing;
            # an own row reads inverted (white plate). The namer handles the
            # own-cluster exclusion, but we skip own rows here for clarity.
            if (self._ocr_namer is not None
                    and not row.is_own
                    and row.native_crop is not None):
                self._ocr_namer.note_crop(
                    driver, row.native_crop,
                    roster_name=self._roster.name_of(driver))

        # **Before the pit rows, because the entry call needs it.** It was
        # computed only for the gaps, below, which is after every announcement
        # has already been made.
        if identified:
            self._stage["named"] += 1
        own = self._own_driver(ids, board)
        if own is not None:
            self._stage["own_driver"] += 1
        # **Remembered, because `_close` runs on frames where our own row is
        # not identifiable** - a visit closed by the stale timer, or by
        # `close_all` at the flag, has no board to read it off.
        if own is not None:
            self._own = own
            # **Exclude the own cluster from OCR** (issue 2, 26 Sep 2026).
            # The own row's bitmap (white plate, dark ink) is the inverse of
            # rival rows.  If it drifts into a rival cluster, OCR on that
            # cluster will read the wrong name.  Mark the cluster as "own" so
            # `OcrNamer.note_crop` never accumulates own-row crops.
            if self._ocr_namer is not None:
                self._ocr_namer.set_own_cluster(own)
        in_lane: set[int] = set()
        saw_pit_columns = False
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
            saw_pit_columns = True
            if own is not None and driver == own:
                self._stage["own_pit_cols"] += 1
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
            self._absent_since.pop(driver, None)
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
                # **Refuse readings above the car's capacity.** GT7's tank is
                # 100 L for almost every car (§3.4).  AV1 compression artefacts
                # occasionally produce digit readings of 261, 351 L — physically
                # impossible. A figure above capacity is not a reading; refuse
                # and log it. CLAUDE.md rule 3: a wrong measurement filed as
                # real is worse than None. (Issue 7, 26 Sep 2026.)
                if litres > FUEL_CAPACITY_MAX_L:
                    _log.info(
                        "pit-wall: %s (driver %d) — fuel read %d L exceeds "
                        "capacity (%d L); refused (AV1/OCR misread?)",
                        self._roster.name_of(driver) or "unnamed",
                        driver, litres, FUEL_CAPACITY_MAX_L)
                else:
                    self._stage["fuel_read"] += 1
                    if own is not None and driver == own:
                        self._stage["own_fuel_read"] += 1
                    visit.readings.append(litres)
            self._announce_entry(driver, visit, lap, own)
            dx0, dy0, dx1, dy1 = pit.disc
            shape = (dx0, dx1 - dx0 + 1, dy1 - dy0 + 1)
            if visit.disc_at is None and litres is not None:
                visit.disc_at = shape
                # **The OPEN is logged, on the first frame a fuel figure
                # backs it.** Logged on the first disc it said "in the lane"
                # 228 times in a race of 17 stops - scenery (critic, 19 Sep).
                # Logged at all so a stop dropped later has a beginning.
                _log.info("pit-wall: %s (driver %d) in the lane on lap %s%s",
                          self._roster.name_of(driver) or "unnamed", driver,
                          lap, " (joined mid-fill)" if visit.partial else "")
            if visit.disc_at is not None:
                if all(abs(a - b) <= DISC_ANCHOR_PX
                       for a, b in zip(shape, visit.disc_at)):
                    code = read_compound(frame[dy0:dy1 + 1, dx0:dx1 + 1])
                    if code:
                        visit.compounds.append(code)
                        visit.last_compound_l = litres
                        visit.last_compound_s = now
                else:
                    self._stage["disc_off_anchor"] += 1

        # **The gaps are noted AFTER the rows are identified**, so each trend
        # knows whose gap it is holding. A trend that does not know that
        # regresses straight through an overtake and reports the new car's
        # distance as our own lost pace.
        if saw_pit_columns:
            self._stage["pit_cols"] += 1
        ahead_gap, behind_gap = read_gaps(frame, board)
        if ahead_gap is not None or behind_gap is not None:
            self._stage["gaps"] += 1
        own_place = self._position.get(own)
        if self._on_board is not None and own is not None:
            try:
                self._on_board(
                    [(place, self._roster.name_of(driver)
                      if driver is not None else None)
                     for place, driver in frame_rows], own_place)
            except Exception:                        # pragma: no cover
                _log.exception("pit-wall: the board hook raised")
        # **Rich row data for the board_reads table.** Fired once per frame
        # after both the roster and the pit-column loop have run, so
        # cluster_id, name, pit_columns and fuel_l are all available.  The
        # controller writes these batched to the DB off the capture thread.
        if self._on_board_reads is not None and frame_rows:
            try:
                rows_data = []
                for place, driver in frame_rows:
                    name = self._roster.name_of(driver) if driver is not None else None
                    visit = self._visits.get(driver) if driver is not None else None
                    in_pit = driver in in_lane if driver is not None else False
                    fuel_l = visit.readings[-1] if (visit and visit.readings
                                                    and in_pit) else None
                    comp = (visit.compounds[-1] if (visit and visit.compounds
                                                    and in_pit) else None)
                    rows_data.append({
                        "at_s": now,
                        "lap": lap,
                        "position": place,
                        "cluster_id": driver,
                        "name": name,
                        "name_source": (self._name_source_of(driver)
                                        if driver is not None else None),
                        "pit_columns": in_pit,
                        "fuel_l": fuel_l,
                        "compound": comp,
                    })
                self._on_board_reads(rows_data)
            except Exception:                        # pragma: no cover
                _log.exception("pit-wall: the board_reads hook raised")
        at_m = self.where()
        for trend, gap, step in ((self.ahead, ahead_gap, -1),
                                 (self.behind, behind_gap, +1)):
            who = self._neighbour(frame_rows, own_row_place, step)
            trend.note(lap, gap, subject=who)
            if gap is not None:
                self.samples.append(GapSample(
                    at_s=now, gap_s=gap, track_s=at_m, lap=lap,
                    position=own_place, subject=who,
                    ok=True, side=trend.side))
                if self._on_gap is not None:
                    try:
                        self._on_gap(trend.side, gap, who,
                                     self._roster.name_of(who)
                                     if who is not None else None)
                    except Exception:                # pragma: no cover
                        _log.exception("pit-wall: the gap hook raised")

        for driver in identified - in_lane:
            self._seen_clean.add(driver)
            place = self._position.get(driver)
            if place is not None and driver != own:
                self._clean_place[driver] = (place, own_place)

        closed = []
        for driver in list(self._visits):
            if driver in in_lane:
                continue
            if driver not in identified:
                # He was not identified this frame, so this frame says
                # nothing about whether he is standing in his box. **Where
                # the row he was last read on did not read, it may still be
                # him in his box - so the run breaks.** It used to be skipped
                # with the count kept, and one washed-out frame, five seconds
                # of a crew hiding the names and two more closed a 19 -> 58 L
                # fill mid-stand on 1 s of real absence (critic, 19 Sep,
                # `interleave.py`). Only HIS row: breaking on any unread row
                # was tried and, replayed over Sardegna Rd 9, held two real
                # stops open 53 s and 90+ s past the exit - unread rows are
                # everywhere. Off the visible board, the count stands.
                last_y = self._row_y.get(driver)
                if last_y is not None and any(
                        abs(y - last_y) <= ROW_MATCH_TOL for y in unread_ys):
                    self._absent[driver] = 0
                    self._absent_since.pop(driver, None)
                continue
            self._absent[driver] = self._absent.get(driver, 0) + 1
            since = self._absent_since.setdefault(driver, now)
            if (self._absent[driver] >= CLOSE_AFTER_CLEAN_FRAMES
                    and now - since >= CLOSE_AFTER_CLEAN_S):
                # **Closed on the clock, not on seeing him leave.** The exit
                # figure is therefore the highest reading anyone got, which is
                # a lower bound on the fill rather than the fill. It is the
                # only close whose last frame is the lane exit, though, so the
                # only one `Visit.left_on` may read a flip from.
                done = self._close(driver, stale=True, on_absence=True)
                if done is not None:
                    closed.append(done)
        return closed + self._close_stale(now)

    def _own_driver(self, ids: dict, board) -> int | None:
        """Which cluster is ours, asked the way `roster.read` asks it.

        **One relation, not two** (rule 13). This used to test the rung
        against the box MIDPOINT within `ROW_MATCH_TOL`, which is the same
        question `roster.read` answers with `is_own_row` - and the two
        disagreed the moment the plate guard began returning whole plates.
        Measured on the Bathurst race of 20 Sep 2026: of the 242 own rows the
        repaired locator reads, the midpoint test reaches only 172, **58.9%
        of frames against 60.3% before the guard** - so the fix that recovered
        the gaps would have left `_own_driver`, and everything gated on it
        including the tablet's board hook, worse than it found them.
        """
        # **Closest to the middle of the plate, not first out of the dict.**
        # `near[0]` was insertion order, which is the board reader's row
        # order and not a statement about which row is ours - the same file
        # settles pit rows with a `min` on distance 150 lines above. The box
        # is a band now rather than a point, so where two rungs fall inside
        # it the nearer one is the answer and the order they were read in is
        # not (rule 3: a guess dressed as a reading).
        near = [y for y in ids if is_own_row(board, y)]
        if not near:
            return None
        middle = (board[1] + board[3]) / 2.0
        return ids[min(near, key=lambda y: abs(y - middle))]

    @staticmethod
    def _neighbour(frame_rows, own_row: int | None, step: int):
        """The driver read on the row next to ours THIS frame, or `None`.

        `None` rather than a guess: a gap whose owner is unknown must not be
        folded into a trend that thinks it knows - and that includes a row
        whose name did not read this frame.

        **It used to be looked up in `_position`, and that turned a board row
        into a car** (Bathurst, 14 Sep 2026, session 176). `_position` is
        sticky: it holds the row every cluster was LAST seen on, including
        cars long gone from the board and one-frame misreads. The lookup
        returned the first cluster in insertion order whose last row was ours
        minus one, whoever was drawn there now. GT7's board is a window
        around the player, so our own row sits at 6 while the race position
        moves, and the row above ours is a slot the whole field passes
        through. One cluster - "78" - held that slot from lap 0 to lap 14
        while we went P11 to P7: 329 gap readings, and the video at those
        moments shows at least nine drivers in that row (Corn_flake,
        Greenmachine 070, X-Man Oce, BustedGun, A.Maidment, Chook, PUNISHED,
        K.Graebs, ZenPhilosopher). Replayed at the live grab rate, the sticky
        lookup named a car that was not on the adjacent row on 738 of 1,233
        frames, and its most-named car was a cluster seen exactly once.

        The gap readout is drawn beside the row next to ours, so the car it
        belongs to is the name read on that row in the same frame. That is
        content, read off the frame the gap came from.
        """
        if own_row is None:
            return None
        wanted = own_row + step
        for place, driver in frame_rows:
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
                # **Closed on the clock, not on seeing him leave.** The exit
                # figure is therefore the highest reading anyone got, which is
                # a lower bound on the fill rather than the fill.
                # **If the visit had at least one fuel reading, it is a
                # left-view stop** - we saw the car in its box but it dropped
                # off the visible board before the fill finished. The exit
                # fuel is UNKNOWN (not max(readings), which would be a lower
                # bound dressed as a reading). Rule 3 and brief part B.
                left = bool(visit.readings)
                if left:
                    visit.left_view = True
                done = self._close(driver, stale=True, left_view=left)
                if done is not None:
                    closed.append(done)
        return closed

    def close_all(self) -> list[Seen]:
        """End every open visit, for the end of a session.

        Stale by definition: a visit still open at the flag is one nobody saw
        end, so its exit figure is the highest reading taken rather than the
        fill.

        **CRITICAL 3 (26 Sep 2026)**: the old implementation never passed
        `left_view`, so a car that left the visible rows within 180 s of the
        flag with ≥ 1 fuel read was silently dropped instead of filed with
        `left_view=True` and `fuel_out_l=None`.  Apply the same
        qualification `_close_stale` uses: if the visit has readings, it left
        view; file it as such rather than discarding it.
        """
        closed = []
        for d in list(self._visits):
            visit = self._visits.get(d)
            left = bool(visit and visit.readings)
            # **fire_on_stop=False** (issue 11, 26 Sep 2026): the caller
            # (controller._stop_pit_wall) iterates the return value and calls
            # _on_rival_stop itself. Letting _close ALSO fire on_stop would
            # file each end-of-race stop twice — once here, once in the loop.
            result = self._close(d, stale=True, left_view=left,
                                 fire_on_stop=False)
            if result is not None:
                closed.append(result)
        return closed

    @staticmethod
    def _is_a_stop(visit) -> bool:
        """The evidence any stop has to meet before it is called one.

        `MIN_READS` fuel readings, watched for `MIN_WATCHED_S`: the same two
        bars `_close` holds a rival's stop to below, stated once so the own
        car's branch cannot run ahead of them again.
        """
        if visit is None or len(visit.readings) < MIN_READS:
            return False
        # **Rule 9 — no max(0.0, ...) on a measurement.** A negative
        # duration means the reference is wrong, not that no time passed.
        # If last_s < started_s the clock faulted; return False (cannot
        # confirm it is a stop) rather than clamping to 0 and checking
        # 0 >= MIN_WATCHED_S — which is also False, but does not say why.
        if visit.last_s < visit.started_s:
            return False
        return (visit.last_s - visit.started_s) >= MIN_WATCHED_S

    def _close(self, driver: int, *, stale: bool = False,
               on_absence: bool = False,
               left_view: bool = False,
               fire_on_stop: bool = True) -> Seen | None:
        # **Per VISIT.** Keyed per driver for the session, a two-stop rival's
        # second entry - the one that decides the end of the race - was silent.
        self._announced.discard(driver)
        visit = self._visits.pop(driver, None)
        if driver == self._own and not self._is_a_stop(visit):
            # **A glimpse is not a stop, ours any more than a rival's** (13 Sep
            # 2026, Suzuka lap 7). The own-car branch used to run before the
            # evidence a rival's stop must meet, so a visit with no fuel read
            # at all - one frame where our white plate passed the white-disc
            # and bright-ink tests - was logged "own stop on lap 7" on a lap
            # he drove at 126.66 s burning 7.1 L. The same line is on file
            # for laps he did not stop on, 7 and 11 Sep. Below the bar it is
            # dropped the way a rival's fragment is, and said as that.
            self._absent.pop(driver, None)
            self._absent_since.pop(driver, None)
            _log.info("pit-wall: pit columns glimpsed on our own row on lap "
                      "%s (%d fuel reads over %.3f s) - not a stop",
                      visit.lap if visit is not None else None,
                      len(visit.readings) if visit is not None else 0,
                      (visit.last_s - visit.started_s)
                      if visit is not None else 0.0)
            return None
        if driver == self._own:
            # **Our own stop is not a rival's.** `read_rows` returns the
            # driver's own row like any other, so without this the wall handed
            # his stop to `rival_book`, which records it against his own name
            # as an opponent - permanently, keyed by name, in a book whose
            # whole purpose is that tonight's stop joins up with the same
            # driver's last one. Nothing downstream could tell such a row from
            # a real one, and every figure drawn from it - his burn, his fill
            # discipline, when he stops - would be this driver's own habits
            # fed back to him as a rival's.
            #
            # It went unseen because `a_frame` could not tell two drivers
            # apart: its rows differed only in name WIDTH, `name_bitmap`
            # normalises to a fixed shape, and all six folded into one cluster
            # - so the car "in the lane" WAS the own row in every test here.
            self._absent.pop(driver, None)
            self._absent_since.pop(driver, None)
            # **Not a rival's - and not thrown away either.** It goes down its
            # own path, `OwnFill`, which nothing that files rivals can read.
            fill = self._own_fill_from(visit, exit_is_a_bound=bool(stale))
            self._own_fills.append(fill)
            _log.info("pit-wall: own stop on lap %s not filed as a rival's - "
                      "kept as ours: in %s L, out %s L, %s L taken, %d reads "
                      "over %s s%s%s", fill.lap, fill.fuel_in_l,
                      fill.fuel_out_l,
                      "?" if fill.litres is None else "%.0f" % fill.litres,
                      fill.reads,
                      "?" if fill.watched_s is None
                      else "%.0f" % fill.watched_s,
                      " (joined mid-fill)" if fill.partial else "",
                      " (exit is a lower bound)" if fill.exit_is_a_bound
                      else "")
            if self._on_own_fill is not None:
                try:
                    self._on_own_fill(fill)
                except Exception:           # pragma: no cover - belt
                    _log.exception("pit-wall: the own-fill hook raised")
            return None
        self._absent.pop(driver, None)
        self._absent_since.pop(driver, None)
        if visit is None or len(visit.readings) == 0:
            # **0 fuel reads means we never saw the fill** - a false column
            # detection, not a stop. Said always, because this is where a
            # whole race of stops vanished without a trace (Sardegna Rd 9).
            # CLAUDE.md rule 10: log the accepts, not only the refusals.
            if visit is not None:
                _log.info(
                    "pit-wall: %s's visit dropped - 0 fuel reads (false "
                    "column detection?) over %.3f s from lap %s; not filed",
                    self._roster.name_of(driver) or f"driver {driver}",
                    visit.last_s - visit.started_s, visit.lap)
            return None
        # **A cluster too rarely seen to be a driver cannot file a stop.**
        # Same run-length argument `Roster.drivers` makes: a real driver is on
        # the board through the race, a misread appears once or twice. Without
        # this the Spa race filed twelve stops for eight drivers, the extra
        # four being two-reading fragments that had founded clusters of their
        # own - and each took a driver handle with it, so the book would have
        # carried four people who never existed into the next race.
        # Counted at most once per `roster.SIGHTING_SPACING_S`, so the floor
        # means the same at a 0.5 s grab as at the 2 s it was set at.
        if self._roster.spaced_sightings(driver) < self._min_sightings:
            _log.info("pit-wall: a stop from a cluster seen only %d times is "
                      "not filed - that is a misread, not a driver",
                      self._roster.spaced_sightings(driver))
            return None
        # **Rule 9 — no max(0.0, ...) on a measurement.** A negative
        # watched duration means the clock reference is wrong (two timestamps
        # from the same monotonic clock should never go backward).  Clamping
        # to 0 would make it look like a zero-second stop — a well-formed
        # reading downstream cannot distinguish from a real one.  Return None
        # instead, which signals "cannot tell" rather than "definitely no".
        raw_watched = visit.last_s - visit.started_s
        if raw_watched < 0:
            _log.info(
                "pit-wall: %s has a negative watched duration (%.3f s — "
                "clock fault?); not filing",
                self._roster.name_of(driver) or f"driver {driver}",
                raw_watched)
            return None
        watched = raw_watched
        if len(visit.readings) < MIN_READS:
            # **Said, because this is where a whole race of stops vanished.**
            # In Sardegna Rd 9 every stop by a car on medium tyres ended here
            # with 0 or 1 fuel reads - Rocky's and Boxhead's among them - and
            # there was not one log line about either, so the defect upstream
            # (a disc refused on shape) could not be seen from the log at
            # all. CLAUDE.md rule 10: log the accepts, not only the refusals -
            # and a refusal that is silent is worse than either.
            #
            # **MIN_READS applies to left_view filings too** (coordinator
            # 26 Sep 2026).  A lone 1-read visit or fragment must never be
            # filed as a stop on its own; left_view only relaxes MIN_WATCHED_S
            # and the exit reading.  A 1-read fragment stays eligible for
            # recombination — the 2+1 PUNISHED path (two clusters watching the
            # same stop, combined ≥ MIN_READS) must still qualify.
            _log.info(
                "pit-wall: %s's visit dropped - %d fuel read(s), %d "
                "needed, over %.0f s from lap %s; not filed%s",
                self._roster.name_of(driver) or f"driver {driver}",
                len(visit.readings), MIN_READS,
                watched, visit.lap,
                " (left_view)" if left_view else "")
            if len(visit.readings) >= 1:
                self._store_fragment(driver, visit)
            return None
        if not left_view and watched < MIN_WATCHED_S:
            _log.info("pit-wall: %s discarded - %d reads over %.0f s is too "
                      "brief to be a stop", self._roster.name_of(driver)
                      or f"driver {driver}", len(visit.readings), watched)
            if len(visit.readings) >= 1:
                self._store_fragment(driver, visit)
            return None
        name = self._name_or_mint(driver)
        # **A fill that did not move was not watched, whatever else happened.**
        # `partial` means the entry figure is an upper bound rather than a
        # measurement, and a visit whose lowest and highest readings are the
        # same number is the strongest possible case of that: nothing was seen
        # to change. Measured on the Spa race, one driver came back 19 L in and
        # 19 L out on two readings - a fragment of a stop that really ran to
        # 83 L. Filed, because he did stop and that is a fact worth keeping,
        # but kept out of anything that computes a rate.
        visit.closed_on_absence = on_absence
        if stale and not left_view and visit.rising_when_last_read:
            # Counted and said, not prevented - see
            # `Visit.rising_when_last_read` for why the readings alone cannot
            # decide this. Counted HERE, where a stop is actually filed and
            # on every stale close - the absence rule's and the silence
            # clock's - and reported in `health()` (critic, 19 Sep: it was
            # counted on absence only, including closes that filed nothing,
            # and printed nowhere).
            self._stage["closed_mid_rise"] += 1
            _log.info("pit-wall: %s (driver %d) closed %s with the tank still "
                      "rising (%s L at the last read) - exit filed as a lower "
                      "bound", name, driver,
                      "on absence" if on_absence else "on the clock",
                      visit.readings[-1])
        stop = visit.as_stop()
        # **left_view means the car dropped off the visible board.** Two cases:
        #
        # 1. Underqualified stop (below MIN_READS or MIN_WATCHED_S): the exit
        #    is genuinely unknown — blank fuel_out_l (rule 3). These are filed
        #    *only* because left_view relaxes the bar.
        #
        # 2. Fully-qualified stop (met MIN_READS and MIN_WATCHED_S): the exit
        #    is max(readings), which IS a lower bound on the fill — not unknown.
        #    Use exit_is_a_bound, not None. Filing None for a 59-read stop is
        #    rule 3 backwards: it makes a measured figure look like a gap.
        #    (Issue 5, 26 Sep 2026 coordinator replay review.)
        well_watched = (len(visit.readings) >= MIN_READS
                        and watched >= MIN_WATCHED_S)
        exit_unknown = left_view and not well_watched
        import dataclasses as _dc
        if exit_unknown:
            stop = _dc.replace(stop, fuel_out_l=None)
        no_fill = (stop.litres is not None and stop.litres <= 0)
        seen = Seen(driver=name, driver_id=driver,
                    stop=stop, reads=len(visit.readings),
                    # Rule 4: the count behind `stop.compound`. A change seen
                    # at the exit rests on ONE frame, not on the vote.
                    compound_reads=(1 if visit.compound_changed
                                    else len(visit.compounds)),
                    watched_s=watched, partial=visit.partial or no_fill,
                    # exit_is_a_bound when: closed stale (not a clean exit),
                    # OR the car left view on a qualified stop (last read is a
                    # lower bound, fill may have continued after it dropped off).
                    exit_is_a_bound=bool(stale and not exit_unknown),
                    left_view=left_view,
                    visit_start_s=visit.started_s,
                    visit_end_s=visit.last_s)
        # **In-memory duplicate guard** (coordinator 26 Sep 2026, Fix 2).
        # Two clusters that watched the same stop will each call _close.  The
        # DB fold (P3-1) deduplicates the row, but on_stop fires BEFORE the
        # DB write, so without this guard the coordinator and tablet receive
        # two stop events for one stop.  Check the already-filed stops for the
        # same driver in the same-visit window; if found, suppress the second
        # filing.  The time check mirrors the DB fold rule: windows that
        # overlap or are within STOP_COMBINE_MAX_GAP_S are the same visit.
        if seen.visit_start_s is not None:
            for existing in self._stops:
                if existing.driver != name:
                    continue
                if (existing.stop.lap is not None and stop.lap is not None
                        and abs(existing.stop.lap - stop.lap) > 1):
                    continue
                if (existing.visit_start_s is None
                        or existing.visit_end_s is None):
                    continue
                dup_gap = (max(existing.visit_start_s, seen.visit_start_s)
                           - min(existing.visit_end_s, seen.visit_end_s))
                if dup_gap <= STOP_COMBINE_MAX_GAP_S:
                    _log.info(
                        "pit-wall: %s lap %s — suppressing duplicate filing "
                        "(already filed in same-visit window, gap %.1f s)",
                        name, stop.lap, dup_gap)
                    return None
        self._stops.append(seen)
        _log.info("pit-wall: %s (driver %d) stopped - in %s L, out %s L, %d "
                  "reads over %.0f s%s%s", seen.driver or "unnamed", driver,
                  visit.entry_l, visit.exit_l, seen.reads, seen.watched_s,
                  " (joined mid-fill)" if seen.partial else "",
                  (" (left view — exit unknown, underqualified)"
                   if exit_unknown
                   else " (left view — exit is a lower bound)"
                   if left_view else ""))
        if fire_on_stop and self._on_stop is not None:
            try:
                self._on_stop(seen)
            except Exception:               # pragma: no cover - belt
                _log.exception("pit-wall: stop handler failed")
        return seen

    # --- OCR callbacks (Part A) -----------------------------------------

    def _ocr_named(self, cluster_id: int, name: str,
                   source: str, score: float, votes: int) -> None:
        """OCR resolved a cluster to a real name: label the roster cluster.

        Called from the OCR namer's worker thread, guarded. The roster's own
        lock protects concurrent access.
        """
        try:
            existing = self._roster.name_of(cluster_id)
            self._roster.label(cluster_id, name)
            _log.info("pit-wall: OCR named cluster %d as %r (was %r, "
                      "source=%s, score=%.2f, votes=%d)",
                      cluster_id, name, existing, source, score, votes)
        except Exception:                           # pragma: no cover - belt
            _log.exception("pit-wall: OCR named callback raised")

    def _store_fragment(self, driver: int, visit: "Visit") -> None:
        """Store a refused sub-threshold visit as a fragment for later merging.

        When two clusters with the same driver are later joined by OCR, the
        combined fragment may meet the stop bar.  Overrides any existing
        fragment for this cluster (only one per cluster is needed, since they
        accumulate readings as the visit ran).
        """
        import time as _t
        closed_at = _t.monotonic()
        self._fragments[driver] = (closed_at, visit)
        _log.debug("pit-wall: fragment stored for cluster %d (%d read(s), "
                   "%.0f s), TTL %.0f s",
                   driver, len(visit.readings),
                   visit.last_s - visit.started_s, FRAGMENT_TTL_S)

    @staticmethod
    def _combine_visits(a: "Visit", b: "Visit") -> "Visit":
        """Merge two Visit objects into one, taking the best of each field.

        Used when OCR identifies two clusters as the same driver.  Not the
        same as an open-visit merge (which merges IDENTICAL reading lists)
        — here the two visits may have read different fuel values at different
        times and we want all of them.
        """
        import dataclasses
        all_readings = sorted(set(a.readings) | set(b.readings))
        return dataclasses.replace(
            a,
            started_s=min(a.started_s, b.started_s),
            last_s=max(a.last_s, b.last_s),
            readings=all_readings,
            compounds=(a.compounds + b.compounds),
            partial=(a.partial or b.partial),
        )

    def _ocr_merge(self, keep_id: int, drop_id: int, name: str) -> None:
        """Two clusters OCR-named to the same person: merge them.

        Called from the OCR namer's worker thread. We call the same
        `_merge_converged` path the roster uses for bitmap-drift merges, but
        only if the two ids are still alive — a cluster that has already been
        aliased is already merged.

        **CRITICAL 2 (26 Sep 2026)**: the old implementation aliased
        drop_id → keep_id in the roster but left an open Visit under
        drop_id.  That Visit then closed as its own stop (under the phantom
        key) while a fresh Visit opened under keep_id — one real stop
        splitting into two filed stops.

        Fix: atomically transfer the drop Visit's readings, started_s,
        compounds and partial flag into keep's Visit (or replace it if
        keep has no open visit) BEFORE the roster merge.
        """
        try:
            import dataclasses
            keep = self._roster._resolve(keep_id)   # noqa: SLF001
            drop = self._roster._resolve(drop_id)   # noqa: SLF001
            if keep == drop:
                return                              # already merged
            # **Transfer open Visit before aliasing** so the stop closes
            # under keep_id, not twice.
            drop_visit = self._visits.pop(drop, None)
            keep_visit = self._visits.get(keep)
            if drop_visit is not None:
                if keep_visit is None:
                    # Simple re-key: continue watching under keep
                    self._visits[keep] = drop_visit
                    _log.info(
                        "pit-wall: OCR merge — moved open visit from "
                        "cluster %d to %d (%d readings so far)",
                        drop, keep, len(drop_visit.readings))
                else:
                    # Both had open visits: combine under keep. Use the
                    # earlier started_s; merge all readings; partial if
                    # either was partial.
                    all_readings = drop_visit.readings + [
                        r for r in keep_visit.readings
                        if r not in drop_visit.readings]
                    merged = dataclasses.replace(
                        keep_visit,
                        started_s=min(drop_visit.started_s,
                                      keep_visit.started_s),
                        readings=sorted(all_readings),
                        compounds=(drop_visit.compounds
                                   + keep_visit.compounds),
                        last_s=max(drop_visit.last_s, keep_visit.last_s),
                        partial=(drop_visit.partial or keep_visit.partial),
                    )
                    self._visits[keep] = merged
                    _log.info(
                        "pit-wall: OCR merge — combined visits cluster %d"
                        " and %d under %d (%d readings combined)",
                        drop, keep, keep,
                        len(merged.readings))
            # Also transfer absent-counter state so close logic is unbroken.
            if drop in self._absent:
                self._absent[keep] = max(
                    self._absent.get(keep, 0), self._absent.pop(drop))
            self._absent_since.pop(drop, None)
            # **OCR identity is the name, not the bitmap distance.**
            # `_merge_converged` checks bitmap distance ≤ SAME_NAME_MAX_DIFF
            # (0.58), but OCR same-driver pairs from AV1 video typically measure
            # 0.61-0.90 — so ~100 of 103 merge calls had no effect in s213/s188.
            # Use `force_merge`, which bypasses the distance check while still
            # honouring the "seen side-by-side in one frame" veto (issue 1,
            # 26 Sep 2026 coordinator replay review).
            self._roster.force_merge(keep, drop, name)
            # **Fragment re-evaluation (fault 3, coordinator 26 Sep 2026).**
            # Sub-threshold visits that were refused when they closed may
            # qualify once their cluster is merged with another — e.g. two
            # clusters that each watched 1-2 s of the same stop combine to
            # cover the full stop duration and meet MIN_READS + MIN_WATCHED_S.
            self._merge_fragments_after_ocr(keep, drop)
        except Exception:                           # pragma: no cover - belt
            _log.exception("pit-wall: OCR merge callback raised")

    def _merge_fragments_after_ocr(self, keep: int, drop: int) -> None:
        """Re-evaluate sub-threshold fragments after an OCR cluster merge.

        Called from ``_ocr_merge`` after the roster merge.  If either cluster
        had a fragment in the holding area, combine them (and any open visit
        under ``keep``) and re-check against the stop bar.  Files via
        ``on_stop`` if the combined visit qualifies.  Expired fragments
        (> FRAGMENT_TTL_S old) are discarded without re-evaluation.
        """
        import time as _t
        now = _t.monotonic()

        keep_entry = self._fragments.pop(keep, None)
        drop_entry = self._fragments.pop(drop, None)

        # Discard expired fragments.
        def _fresh(entry):
            if entry is None:
                return None
            closed_at, visit = entry
            if now - closed_at > FRAGMENT_TTL_S:
                _log.debug("pit-wall: fragment for cluster expired (%.0f s old)",
                           now - closed_at)
                return None
            return visit

        keep_frag = _fresh(keep_entry)
        drop_frag = _fresh(drop_entry)

        if keep_frag is None and drop_frag is None:
            return  # nothing to re-evaluate

        # **P3-2**: require time proximity before combining two fragments.
        # Two fragments separated by more than STOP_COMBINE_MAX_GAP_S cannot
        # be from the same pit stop — a GT7 stop cannot restart within that
        # gap.  If they are too far apart, evaluate the keep fragment alone and
        # discard the drop fragment (the drop cluster has already been merged
        # into keep by _ocr_merge; there is nowhere else for it to go).
        if keep_frag is not None and drop_frag is not None:
            gap = (max(keep_frag.started_s, drop_frag.started_s)
                   - min(keep_frag.last_s, drop_frag.last_s))
            if gap > STOP_COMBINE_MAX_GAP_S:
                _log.info(
                    "pit-wall: fragments for clusters %d and %d are %.0f s "
                    "apart (max %.0f s); not combining — keep fragment "
                    "evaluated alone, drop fragment discarded",
                    keep, drop, gap, STOP_COMBINE_MAX_GAP_S)
                drop_frag = None

        # Combine fragments with each other, applying the P3-4 consistency
        # check on every 1-read fragment before it is merged.
        combined: "Visit | None" = None
        for v in filter(None, [keep_frag, drop_frag]):
            if combined is None:
                combined = v
            else:
                # **P3-4**: a 1-read fragment combined into a multi-read visit
                # must have its single reading within the other visit's fuel
                # range.  A garbage OCR digit (e.g. 3 L on a car filling from
                # 40 L) can be stored as a fragment but must not corrupt the
                # real reading set.  Check applies in both directions: if the
                # incoming fragment has 1 read, check it against the combined;
                # if the combined has 1 read, check it against the incoming.
                if len(v.readings) == 1 and combined.readings:
                    single = v.readings[0]
                    entry = min(combined.readings)
                    exit_l = max(combined.readings)
                    if not (single >= entry - _FRAGMENT_FUEL_TOLERANCE_L
                            and single <= exit_l):
                        _log.info(
                            "pit-wall: 1-read fragment (%d L) is inconsistent "
                            "with combined readings %s (entry %d, exit %d, "
                            "tolerance %d L); fragment dropped",
                            single, combined.readings, entry, exit_l,
                            _FRAGMENT_FUEL_TOLERANCE_L)
                        continue  # skip this fragment
                elif len(combined.readings) == 1 and v.readings:
                    single = combined.readings[0]
                    entry = min(v.readings)
                    exit_l = max(v.readings)
                    if not (single >= entry - _FRAGMENT_FUEL_TOLERANCE_L
                            and single <= exit_l):
                        _log.info(
                            "pit-wall: existing 1-read combined (%d L) is "
                            "inconsistent with incoming readings %s (entry %d,"
                            " exit %d); replacing with the larger visit",
                            single, v.readings, entry, exit_l)
                        combined = v
                        continue
                combined = self._combine_visits(combined, v)

        open_visit = self._visits.get(keep)
        if open_visit is not None and combined is not None:
            # **P3-2 (open-visit branch)**: also check proximity against the
            # open visit.  A fragment from a different stop should not be
            # merged into the current one.
            gap = (max(open_visit.started_s, combined.started_s)
                   - min(open_visit.last_s, combined.last_s))
            if gap > STOP_COMBINE_MAX_GAP_S:
                _log.info(
                    "pit-wall: combined fragment (started %.0f s) is %.0f s "
                    "from the open visit (started %.0f s); not merging into "
                    "open visit — evaluating fragment alone",
                    combined.started_s, gap, open_visit.started_s)
            else:
                # Extend the OPEN visit with the fragment readings so that
                # when it closes naturally it has the full evidence.
                import dataclasses
                extended = dataclasses.replace(
                    open_visit,
                    started_s=min(open_visit.started_s, combined.started_s),
                    readings=sorted(
                        set(open_visit.readings) | set(combined.readings)),
                    compounds=(open_visit.compounds + combined.compounds),
                    partial=(open_visit.partial or combined.partial),
                )
                self._visits[keep] = extended
                _log.info(
                    "pit-wall: fragment merged into open visit for cluster %d "
                    "(%d → %d readings)", keep,
                    len(open_visit.readings), len(extended.readings))
                return

        if combined is None:
            return

        # No open visit: re-evaluate the combined fragment directly.
        # Always treat as left_view (car already dropped off the board).
        # Temporarily place in _visits so _close can process it.
        if keep in self._visits:
            return   # open visit appeared between pop and here; skip

        # **Log-spam guard (coordinator 26 Sep 2026).**
        # If the combined visit is still below the filing threshold, put it
        # back silently without calling _close.  The "not filed" line already
        # fired once when the fragment first entered the holding area; a
        # re-evaluation that changes nothing must not fire it again.  Each
        # re-evaluation that adds no reads is also pure overhead, so skip the
        # _close path entirely here.
        if len(combined.readings) < MIN_READS:
            self._fragments[keep] = (now, combined)
            return

        self._visits[keep] = combined
        result = self._close(keep, stale=True, left_view=True)
        if result is not None:
            _log.info(
                "pit-wall: fragments re-evaluated and filed for cluster %d "
                "(%s, %d reads, lap %s)",
                keep, name if (name := self._roster.name_of(keep)) else "?",
                len(combined.readings), combined.lap)
        else:
            _log.debug(
                "pit-wall: combined fragment for cluster %d still "
                "sub-threshold after merge (%d reads)", keep,
                len(combined.readings))

    def _ocr_rename(self, old_name: str, new_name: str) -> None:
        """OCR replaced a phantom handle with a real name: update filed stops.

        Called from the OCR namer's worker thread. Updates the `_stops` list
        for this session — the coordinator's filed `Rival` objects are keyed
        by name, so renaming them here keeps the live race's bookkeeping
        consistent.

        **Also fires `on_ocr_rename(old_name, new_name)`** (CRITICAL 1) so
        the controller can rename this session's DB rows only.  Past sessions
        must not be touched by a live OCR event.
        """
        try:
            import dataclasses
            count = 0
            for i, stop in enumerate(self._stops):
                if stop.driver == old_name:
                    self._stops[i] = dataclasses.replace(stop,
                                                         driver=new_name)
                    count += 1
            _log.info("pit-wall: renamed %r -> %r in %d filed stop(s)",
                      old_name, new_name, count)
            if self._on_ocr_rename is not None:
                try:
                    self._on_ocr_rename(old_name, new_name)
                except Exception:                  # pragma: no cover - belt
                    _log.exception("pit-wall: OCR rename DB callback raised")
        except Exception:                          # pragma: no cover - belt
            _log.exception("pit-wall: OCR rename callback raised")

    # --- naming ---------------------------------------------------------

    def _name_source_of(self, driver: int) -> str | None:
        """The source of this cluster's name: 'ocr', 'handle', 'exemplar', or None.

        Used to populate ``board_reads.name_source`` with a real value
        instead of the hardcoded ``'bitmap'`` that was there before
        (IMPORTANT 6, 26 Sep 2026).

        - ``'ocr'``      — resolved by Windows.Media.Ocr and matched against
                          the league vocabulary (``OcrNamer._resolved``).
        - ``'handle'``   — a provisional ``Car #N`` handle minted because the
                          roster had no exemplar for this cluster.  The driver
                          turns it into a person later; a rename carries the
                          stops with it.
        - ``'exemplar'`` — matched against a hand-labelled bitmap from the
                          archive (the normal path for returning drivers).
        - ``None``       — no name yet.
        """
        name = self._roster.name_of(driver)
        if name is None:
            return None
        # OCR wins if the namer has a resolution for this cluster.
        if (self._ocr_namer is not None
                and self._ocr_namer.resolved_name(driver) is not None):
            return "ocr"
        # A provisional handle is any phantom name (e.g. "Car #N" or "F#N").
        from pitcrew.telemetry.ocr_namer import _is_phantom
        if _is_phantom(name):
            return "handle"
        return "exemplar"

    def named(self, min_sightings: int | None = None) -> list[tuple[int, str]]:
        """Driver ids that are worth a name, commonest first.

        The ones with no name yet are the ones a person has to label once. A
        proportional mixed-case font is not something this app guesses at.
        """
        if min_sightings is None:
            min_sightings = self._min_sightings
        return [(d, self._roster.name_of(d) or "")
                for d in list(self._roster.drivers(
                    min_sightings=min_sightings, spaced=True))]
