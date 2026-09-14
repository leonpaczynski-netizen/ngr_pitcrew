"""What is going on in the race around him - volunteered, and held to the noise.

The driver, 14 Sep 2026, after Bathurst Rd7: *"want more comms from him about
what is going on in the race."* His decision, recorded in
`docs/ENGINEER-TARGET-STATE_2026-08-29.md` D7: George volunteers four things,
with **no per-lap talk cap** ("talk whenever it matters"). And no limit on
where: *"George can speak at anytime."* (15 Sep 2026). Instructions go first
and a line waits only behind other speech - the voice's classes decide that,
not this module.

What this module decides is WHETHER a fact is worth a word, and what the word
may claim. In the order the coordinator offers them (`calls.URGENCY`):

1. **What the stops mean for us** (`STOPS_PICTURE`, plan row 1.3).
   "P6 on the road. 2 ahead still to stop." while cars ahead of us still owe
   the stop we owe too; once every car ahead has stopped, or we have,
   "P6 on the road. Effectively P8 after the stops. If they stop once."
2. **Pace against the car ahead or behind** (`PACE`).
   "Catching PUNISHED, 0.9 seconds a lap. Over 5 laps."
3. **A championship rival from the brief's watch list** (`WATCHED`).
   "Magical daddy P4, 3 ahead."
4. **The gaps, with names** (`GAPS`). "PUNISHED ahead, 2.1. K.Graebs behind,
   0.6."

### Rule 13, in the vocabulary

"Ahead" and "behind" are always the on-road neighbour. "Effectively" is always
after the stops, and is never said without "on the road" beside it. A handle
the roster minted for a car nobody has named - "Car #76" - is said as "the car
ahead" or "the car behind": it is not a person, and read aloud it came out as
"Car hash 76".

### What each rests on, and what it may not claim

**Gaps** are GT7's own interval boxes as the pit wall reads them. Measured off
`gap_reads` (sessions 143, 160, 166, 176; 3,575 readings): two readings of one
car under 4 s apart differ by a median 0.03-0.11 s. So a gap is said to a
tenth under `TENTHS_BELOW_S` and in whole seconds above it - a five-second gap
queued behind a box call moves by more than a tenth before it is heard. The
NAME is the weaker half: the board's clusters split one driver into several
handles and, at session 176, merged several drivers into one, so a gap line
is MEDIUM and the name is only ever the roster's.

**And a figure is only said continuous with the car it is about** (15 Sep
2026). The subject of a gap is the car in the slot, not the handle: a reading
that jumps further than one car's gap can move (`jump_allowed_s`) is held
until three agree, and a figure he would hear as a jump from the last one on
that side is not said unless a place change, a rival's stop or our own off
or stop lies between. A handle seen holding the slot across a place change
names a slot - no name, no pace off it; one whose readings jump twice with
nothing to explain it is said "Unconfirmed.". See `JUMP_RATE_S_PER_S`.

**The stop cycle** knows who stopped (the pit wall's lane log) and nobody's
plan but ours. **A rival's remaining stops are assumed to be the regulation
minimum** - `events.mandatory_stops`, or our own plan's stop count where the
event states none - and the sentence says so ("If they stop once."). Where
the board cannot see every car it counts - GT7 draws about eight rows, and a
car near the cut drops below it exactly while it stands in its box
(memory: board truncation) - the call is LOW and ends "Unconfirmed.".

**A place off the board** is converted from the ROW the reader saw it on. The
board is not positions 1-8: it draws the top three and then a window around
the player's own row (measured 12 Sep 2026 on Daytona session 142 and Bathurst
session 160). With our own place from the packet and our own row from the
board, the rows below the top three map to places; any board that does not fit
that shape is refused rather than guessed (rule 3). A rival who is not on the
board is not given a place at all.

**Pace** is the hardest claim and the one CLAUDE.md's noise lesson bounds.
See `pace_verdict`: the board's own five-lap rule, and on top of it a test that
the lap-to-lap change in the gap - his lap time less ours, `race/rival_pace.py`
- has a 95% interval that excludes zero, over laps where neither car was in
the lane and we had no incident. Measured on the same four sessions, adjacent
laps of one car differ with a standard deviation of 0.8-5 s, so this will be
silent most races. That is the direction this codebase has chosen every time:
it misses real trends rather than inventing them.

### Said means heard

Every call built here is booked - the gap bands, the place, the pace figure -
only when the voice says it was heard (`RaceCoordinator._book`), and released
untouched when it was not, so the next offer is built from the race as it is
then. Rule 11: `new_session` empties all of it, and the coordinator calls it
on arming.

### Threads

Gap readings and board reads arrive on the pit wall's worker thread; calls are
built on the telemetry thread; bookings land on the Qt thread. One lock guards
the mutable state and nothing is held across a call out.
"""
from __future__ import annotations

import math
import re
import threading
from collections import deque
from dataclasses import dataclass, replace
from statistics import mean, stdev

from pitcrew.diagnostics import log
from pitcrew.race.calls import (GAPS, LOW, MEDIUM, PACE, STOPS_PICTURE,
                                WATCHED, Call)
from pitcrew.race.gaps import MIN_LAPS_FOR_TREND, GapTrend, trend_words
from pitcrew.race.rival_pace import RivalPace
from pitcrew.race.tow import CLEAR_GAP_S, HELD_UP_GAP_S
from pitcrew.telemetry.recorder import SAMPLE_HZ

# --------------------------------------------------------------- the numbers

# **A reading older than this is not the gap now.** The wall reads the board
# every two to four seconds when it can (session 176: 16-44 readings a side per
# lap of ~125 s), so twelve seconds is three missed readings in a row.
GAP_FRESH_S = 12.0
# **Consecutive readings of one car before he is the car ahead.** At session
# 176 single readings carried another name on six of fourteen laps - a board
# row misread - and `GapTrend` already refuses to let one reading rewrite the
# history. Three in a row is six to twelve seconds of the same car.
NEIGHBOUR_HOLD_READS = 3
# **The bands a gap is news for crossing**, and they are the codebase's own
# words rather than new ones (rule 13): inside `tow.HELD_UP_GAP_S` (1.5 s) the
# gap reads as traffic and a tow; outside `tow.CLEAR_GAP_S` (3.0 s) he is in
# clear air, beyond a tow's reach. Crossing either changes how he drives.
BANDS_S = (HELD_UP_GAP_S, CLEAR_GAP_S)
# How far past a band a gap has to be before it has crossed it. The 90th
# percentile of the reader's own disagreement between two readings seconds
# apart was 0.13-0.37 s; 0.15 each side is a 0.3 s dead band.
BAND_HYSTERESIS_S = 0.15
# **The refresher**: at most once a lap, and only while either car is this
# close. Beyond it nobody is racing him, and a number every lap about a car
# twenty seconds away is the table §5.5 forbids.
REFRESH_WITHIN_S = 5.0
# A tenth below this, whole seconds above - see the module docstring.
TENTHS_BELOW_S = 5.0
# Seconds a place picture must hold before it is said - the position call's own
# hold (`calls.POSITION_HOLD_FRAMES`), so the two agree on "settled".
PICTURE_HOLD_S = 8.0
# A board read older than this does not describe the order now.
BOARD_FRESH_S = 12.0
# The rows GT7 always draws from the top before the window round his own row.
TOP_ROWS = 3
# **A pace figure is said again only when it has moved this much**, per side
# and per car. Half a second a lap is about the spread of a five-lap rate with
# nothing happening (`gaps.TREND_WORTH_SAYING_S`'s note: 0.48-0.62 at s143).
PACE_REPEAT_S_PER_LAP = 0.5
# A watched rival's place is said again, without a change of side or a stop,
# no sooner than this.
WATCHED_REPEAT_S = 60.0
# Two-sided 95% points of Student's t, by degrees of freedom.
T_975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
         7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
# The fewest clean lap-to-lap changes a pace verdict may rest on.
PACE_MIN_CHANGES = 3

# ------------------------------------------------ one car, or several
#
# **A gap figure is only said continuous with the car it is about.** Replayed
# at Bathurst (session 176) George said "The car ahead, 0.5." and thirty
# seconds later "The car ahead, 9 seconds." The board's unnamed cluster "78"
# held the ahead box for fifteen laps and six places: it is a slot, not a car.
# Both figures were GT7's own interval box, read right - a pass sat between
# them - but a single "car ahead" across them is several cars, and heard back
# to back they are a jump no car makes.
#
# **How far one car's gap can move** (gap_reads, sessions 143/160/166/176:
# consecutive readings of one handle and side, under 8 s apart, on laps with
# no pit, lane visit or off of ours - 1,066 pairs, median 2.2 s apart): the
# rate of change has a median of 0.02 s/s and a 99th percentile of 0.25 s/s.
# Two readings of one car under 3 s apart differ by a 99th percentile of
# 0.57 s. So a reading is the same car where it moved no more than
# `JUMP_NOISE_S + JUMP_RATE_S_PER_S` x seconds since the last one. That
# envelope passes 1,061 of the 1,066 pairs; the five it refuses are all
# 1.8-7.7 s jumps inside 2-7 s, among them the lap-6 pass above.
#
# **A corner's burst is not a sustained rate.** A quarter second a second for
# thirty seconds is 7.5 s, which let "0.5" then "9 seconds" through as one
# car. Over longer spans, inside chains of readings each continuous with the
# last (same sessions and filter, 17,414 pairs up to 120 s apart), the 99.9th
# percentile change is 0.9 s at 3 s, 2.9 s at 30-45 s, 3.8 s at 45-60 s and
# 5.8 s at 90-120 s. `JUMP_BURST_S + DRIFT_S_PER_S` x seconds caps the rate
# from about 5 s on and passes all but 7 of those pairs.
JUMP_NOISE_S = 0.5
JUMP_RATE_S_PER_S = 0.25
JUMP_BURST_S = 1.0
DRIFT_S_PER_S = 0.05
# **Readings that must agree before a jump is a new car.** Replaying that
# envelope over the same four sessions' handles: a run of readings that broke
# from the car and agreed among themselves, then was abandoned inside 30 s,
# was one or two readings long on laps clean of our stops and offs (3 runs)
# and never three. Runs of 3, 4 and 6 were abandoned only on our own stop and
# off laps (session 176 laps 9, 11 and 13), where our off or stop is in the
# reading's moment and nothing is volunteered while he regathers. Three
# readings is 4-12 s at the wall's 2-4 s cadence, and it is
# `NEIGHBOUR_HOLD_READS` - "a new car" is held to one rule whether the name
# changed or the figure did.
SUBJECT_HOLD_READS = 3
# **Rule 10: a reference that disagrees with everything is the thing that is
# wrong.** This many readings running that fit neither the car nor each other
# retire the car: nothing is said about that side until three readings agree.
RETIRE_AFTER_REFUSALS = 6
# **Jumps nothing on the circuit explains before a handle is not believed.**
# A jump across a place change, a stop or an off is a different car in the
# slot; one without any of them is the reader, and twice in a race is a habit.
UNRELIABLE_AFTER_JUMPS = 2
# **Seconds the interval box can trail the event that changed its car.**
# Session 176, lap 8: the place was lost at 20:35:25 and the box still showed
# the old car ahead (5.93 s) at 20:35:25, the new one (0.68 s) from 20:35:30;
# and the replay's place changes are the ledger's calls less their 8 s hold,
# good to a few seconds. An event up to this long before the car's last
# reading still explains a jump after it.
EXPLAIN_LAG_S = 10.0

# A provisional handle the store mints for a car nobody has named.
_HANDLE = re.compile(r"^Car #\d+$")

SIDES = ("ahead", "behind")


def packets(seconds: float) -> int:
    return int(seconds * SAMPLE_HZ)


def continuous(before_gap: float, before_packet: int, gap: float,
               packet: int) -> bool:
    """Whether a gap could be the same car's as one read `packet - before`
    frames earlier - see `JUMP_RATE_S_PER_S` and `DRIFT_S_PER_S`."""
    seconds = max(0, int(packet) - int(before_packet)) / SAMPLE_HZ
    return abs(float(gap) - float(before_gap)) <= jump_allowed_s(seconds)


def jump_allowed_s(seconds: float) -> float:
    """How far one car's gap can move in `seconds`."""
    return JUMP_NOISE_S + min(JUMP_RATE_S_PER_S * seconds,
                              JUMP_BURST_S + DRIFT_S_PER_S * seconds)


def a_person(name: str | None) -> str | None:
    """The name, where it names a person; None for a minted handle or none."""
    if not name:
        return None
    name = str(name).strip()
    if not name or _HANDLE.match(name) or name.isdigit():
        return None
    return name


# ------------------------------------------------------------- the wording

def gap_figure(gap_s: float) -> str:
    """A gap in the precision the reading supports."""
    tenths = round(gap_s, 1)
    if tenths < 0.1:
        return "under a tenth"
    if tenths < TENTHS_BELOW_S:
        return f"{tenths:.1f}"
    whole = int(round(gap_s))
    return f"{whole} seconds"


def gap_sentence(side: str, name: str | None, gap_s: float) -> str:
    """ "PUNISHED ahead, 2.1." / "The car behind, 12 seconds." """
    who = a_person(name)
    head = f"{who} {side}" if who else f"The car {side}"
    return f"{head}, {gap_figure(gap_s)}."


def pace_sentence(side: str, name: str | None, rate: float) -> str:
    """The closing rate in words for `side`, the board's words (`trend_words`).

    `rate` is `GapTrend.closing_s_per_lap`'s: positive is the gap shrinking.
    """
    who = a_person(name)
    figure = f"{abs(rate):.1f} seconds a lap"
    if side == "ahead":
        them = who or "the car ahead"
        if rate > 0:
            return f"Catching {them}, {figure}."
        return f"Losing {figure} to {them}."
    them = who or "the car behind"
    if rate > 0:
        return f"{them[0].upper()}{them[1:]} is catching, {figure}."
    return f"Pulling away from {them}, {figure}."


def pace_reason(laps: int) -> str:
    """The count the rate rests on, said with it (rule 4)."""
    return f"Over {laps} laps."


def if_they_stop(required: int) -> str:
    """The assumption behind "effectively", said with it (rule 5)."""
    if required == 1:
        return "If they stop once."
    if required == 2:
        return "If they stop twice."
    return f"If they stop {required} times."


def picture_words(position: int, line: tuple, required: int) -> tuple[str, str]:
    """`(call, reason)` for the stop picture."""
    call = f"P{position} on the road."
    what, value = line
    if what == "still":
        return call, f"{value} ahead still to stop."
    return call, f"Effectively P{value} after the stops. {if_they_stop(required)}"


def watched_sentence(name: str, place: int, ours: int) -> str:
    """ "Magical daddy P4, 3 ahead." - on-road places between us."""
    between = ours - place
    if between == 1:
        where = "the car ahead"
    elif between == -1:
        where = "the car behind"
    elif between > 0:
        where = f"{between} ahead"
    else:
        where = f"{-between} behind"
    return f"{name} P{place}, {where}."


# ---------------------------------------------------------------- the board

@dataclass(frozen=True)
class BoardRead:
    """One frame of the board as places, not rows."""
    packet: int
    places: dict            # name -> place, names seen once only
    visible: frozenset      # every place a row was drawn at, named or not
    windowed: bool


def board_places(rows, own_row: int | None,
                 our_position: int | None) -> tuple[dict, frozenset, bool] | None:
    """`(places by name, every place drawn, windowed)` from one frame's rows.

    `rows` are `(row, name)` with the row 1-based down the board and `name`
    None where the roster has no name. **Refused, not guessed**, where the
    board does not fit the one shape it was measured to have: rows equal to
    places (a short field, or him near the front), or the top `TOP_ROWS` and a
    contiguous window round his own row. A name read on two rows of one frame
    is one of them misread, and neither is kept.
    """
    if own_row is None or not our_position:
        return None
    own_row, our_position = int(own_row), int(our_position)
    if own_row == our_position:
        offset, windowed = 0, False
    elif TOP_ROWS < own_row < our_position:
        offset, windowed = our_position - own_row, True
    else:
        return None
    places: dict[str, int] = {}
    doubled: set[str] = set()
    visible: set[int] = set()
    for row, name in rows:
        row = int(row)
        place = row if (not windowed or row <= TOP_ROWS) else row + offset
        visible.add(place)
        if not name:
            continue
        if name in places:
            doubled.add(name)
        places[name] = place
    for name in doubled:
        places.pop(name, None)
    return places, frozenset(visible), windowed


# ----------------------------------------------------------------- the pace

@dataclass(frozen=True)
class PaceVerdict:
    """A pace difference that beat the noise, and what it rests on."""
    side: str
    subject: str
    name: str | None
    rate: float                 # the board's closing rate, completed laps
    laps: int
    gain_s_per_lap: float       # mean of his lap less ours; + is us quicker
    half_width_s: float         # 95% half-width of that mean
    changes: int
    first_lap: int
    last_lap: int


def pace_verdict(trend: GapTrend | None, side: str, pace: RivalPace | None,
                 ours_s: dict, *, now_key: int | None,
                 dirty_keys: frozenset = frozenset()
                 ) -> tuple[PaceVerdict | None, str]:
    """`(verdict, why not)`: a pace difference only where it beats the noise.

    **The test, in order, and each one refuses:**

    1. **Completed laps only.** The lap in progress has a partial gap in it.
    2. **The board's own rule** - `gaps.trend_words` over the trimmed-median
       rate: five CONSECUTIVE laps of the same car and at least
       `TREND_WORTH_SAYING_S` (0.8 s) a lap. The ear never claims what the
       eye calls "steady", and the figure said is that rate.
    3. **Every lap in that window clean**: not our pit, out or incident lap,
       not a lap he was in the lane, and filed by `RivalPace` (whose lap time
       is ours less or plus the change in the gap).
    4. **The mean of his lap less ours** over those four lap-to-lap changes
       has a two-sided 95% Student-t interval that excludes zero, from the
       changes' own standard deviation - the residual noise of THIS car on
       THIS night, not a constant. A gap is a random walk; its increments are
       the independent quantity, which is why the test is on them and not on
       a line fitted to the gap.
    5. **The two agree in direction.**
    """
    if trend is None or pace is None or now_key is None:
        return None, "no gap history"
    completed = {k: v for k, v in dict(trend.seen).items() if k < now_key}
    done = replace(trend, seen=completed)
    rate, laps = done.closing_s_per_lap()
    if trend_words(side, rate, laps) is None:
        return None, (f"the board's rule: {laps} consecutive laps"
                      + (f", {rate:+.2f} s/lap" if rate is not None else ""))
    window = done._window(MIN_LAPS_FOR_TREND)
    subject = str(trend.subject)
    if pace.subject != subject:
        return None, "the pace record is about another car"
    changes = []
    for key in window[1:]:
        if key in dirty_keys:
            return None, f"lap key {key} is excluded (pit, incident or lane)"
        if key in pace.excluded:
            return None, f"lap key {key}: {pace.excluded[key]}"
        theirs = pace.lap_times_s.get(key)
        ours = ours_s.get(key)
        if theirs is None or ours is None:
            return None, f"lap key {key} has no derived lap time"
        changes.append(theirs - ours)
    if len(changes) < PACE_MIN_CHANGES:
        return None, f"{len(changes)} clean lap changes"
    gain = mean(changes)
    spread = stdev(changes) if len(changes) > 1 else 0.0
    t = T_975.get(len(changes) - 1, 2.0)
    half = t * spread / math.sqrt(len(changes))
    if abs(gain) <= half:
        return None, (f"inside the noise: {gain:+.2f} +/- {half:.2f} s/lap "
                      f"over {len(changes)} laps")
    # Ahead, a closing gap is us quicker (gain > 0); behind, a closing gap
    # is HIM quicker (gain < 0).
    if (rate > 0) != ((gain > 0) if side == "ahead" else (gain < 0)):
        return None, "the rate and the lap times disagree in direction"
    return PaceVerdict(side=side, subject=subject, name=None, rate=rate,
                       laps=laps, gain_s_per_lap=gain, half_width_s=half,
                       changes=len(changes), first_lap=window[0],
                       last_lap=window[-1]), ""


# ------------------------------------------------------------------ the news

@dataclass(frozen=True)
class _Read:
    packet: int
    gap_s: float
    key: str
    name: str | None
    lap_key: int | None
    # **What could have put another car in the slot, or moved one's gap**:
    # `(our place changes, rival lane entries and exits, our offs, our stint
    # index, in our box)` - `RaceCoordinator._slot_moment`. The first two are
    # other cars, the rest are ours. Two readings with the same moment have
    # nothing between them but the circuit. `None` where the caller cannot
    # say.
    moment: tuple | None = None
    # The moment `EXPLAIN_LAG_S` before this reading: an event that recent
    # may not have reached the interval box yet.
    moment_before: tuple | None = None


def _explained(before: tuple | None, after: tuple | None) -> bool:
    """Whether a place change, a stop or an off lies between two moments."""
    if before is None or after is None:
        return False
    return tuple(before) != tuple(after)


def _ours_between(before: tuple | None, after: tuple | None) -> bool:
    """Whether an off or a stop of OURS lies between two moments."""
    if before is None or after is None:
        return False
    return tuple(before)[2:] != tuple(after)[2:]


class RaceNews:
    """The race around him, as four volunteered calls. One per race."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.new_session()

    def new_session(self) -> None:
        """CLAUDE.md rule 11: every figure here is about one race."""
        with self._lock:
            self._reads = {side: deque(maxlen=16) for side in SIDES}
            self._trends = {side: GapTrend(side=side) for side in SIDES}
            self._neighbour: dict[str, str | None] = {s: None for s in SIDES}
            self._neighbour_name: dict[str, str | None] = {
                s: None for s in SIDES}
            self._band: dict[str, int | None] = {s: None for s in SIDES}
            self._band_pending: dict[str, tuple | None] = {
                s: None for s in SIDES}
            # `(identity, band, the reading said)` - see `gaps_call`.
            self._said_gap: dict[str, tuple | None] = {s: None for s in SIDES}
            self._gap_lap: int | None = None
            # One car in the slot: the last reading that was continuous with
            # it, the readings since that broke from it and agree among
            # themselves, how many running fit nothing, and a count that
            # makes a new car in the slot a new identity under one handle.
            self._ref: dict[str, _Read | None] = {s: None for s in SIDES}
            self._run: dict[str, list] = {s: [] for s in SIDES}
            self._refused: dict[str, int] = {s: 0 for s in SIDES}
            self._segment: dict[tuple, int] = {}
            self._key_ref: dict[tuple, _Read] = {}
            # Handles that are not one car this race, and why; unexplained
            # jumps per handle; the lap keys a handle changed car on.
            self._merged: dict[str, str] = {}
            self._unreliable: dict[str, str] = {}
            self._jumps: dict[str, int] = {}
            self._broke_on: dict[str, set] = {}
            # (frame, moment) of recent readings, both sides - `moment_before`.
            self._moments: deque = deque(maxlen=64)
            self._pace = {side: RivalPace() for side in SIDES}
            self._ours_s: dict[int, float] = {}
            self._dirty: set[int] = set()
            self._said_pace: dict[str, tuple | None] = {
                s: None for s in SIDES}
            self._board: BoardRead | None = None
            self._board_before: BoardRead | None = None
            self._said_watch: dict[str, tuple] = {}
            self._watch_stops_told: set[str] = set()
            self._picture_pending: tuple | None = None
            self._said_picture: tuple | None = None
            self._offers: dict[int, tuple] = {}

    # ------------------------------------------------------------ the feeds

    def note_gap(self, side: str, gap_s: float | None, subject=None,
                 name: str | None = None, *, packet: int,
                 lap_key: int | None, moment: tuple | None = None) -> None:
        """One interval box read. Worker thread.

        `subject` is the roster's cluster id, `name` its name where it has
        one. The car is keyed on the name where there is one, so a trend and
        a lane visit can be matched. `moment` is `_Read.moment`.

        **The car in the slot is the last reading continuous with it**
        (`continuous`). A reading that breaks from it is held with any that
        follow and agree among themselves; `SUBJECT_HOLD_READS` of them are a
        new car under the same handle, and nothing is said of that side
        meanwhile (`gaps_call` speaks only the car's own latest reading).
        """
        if side not in SIDES or gap_s is None:
            return
        key = str(name or subject) if (name or subject is not None) else None
        if key is None:
            return
        moment = tuple(moment) if moment is not None else None
        with self._lock:
            history = self._moments
            history.append((int(packet), moment))
            cutoff = int(packet) - packets(EXPLAIN_LAG_S)
            older = [then for at, then in history if at <= cutoff]
            before = older[-1] if older else history[0][1]
            read = _Read(packet=int(packet), gap_s=float(gap_s), key=key,
                         name=name, lap_key=lap_key, moment=moment,
                         moment_before=before)
            reads = self._reads[side]
            reads.append(read)
            if lap_key is not None:
                self._trends[side].note(lap_key, gap_s, subject=key)
            if self._neighbour[side] != key:
                recent = list(reads)[-NEIGHBOUR_HOLD_READS:]
                if (len(recent) == NEIGHBOUR_HOLD_READS
                        and all(r.key == key for r in recent)
                        and _agree(recent)):
                    log("race").info(
                        "news: the car %s is now %s at %.2f s (%d readings "
                        "that agree)", side, name or key, gap_s,
                        NEIGHBOUR_HOLD_READS)
                    self._neighbour[side] = key
                    self._neighbour_name[side] = name
                    # **A handle back in the box after another's readings is
                    # the car it was** where its gap is still his - a name
                    # flicker is not a new car to announce.
                    prior = self._key_ref.get((side, key))
                    same = prior is not None and (
                        continuous(prior.gap_s, prior.packet, gap_s,
                                   read.packet)
                        or _ours_between(prior.moment_before, read.moment))
                    self._new_car(side, read, another=not same)
                return
            self._neighbour_name[side] = name
            self._follow(side, read)

    def one_car(self, key: str) -> bool:
        """Whether a handle is still taken to be one car this race."""
        with self._lock:
            return key not in self._merged and key not in self._unreliable

    def _new_car(self, side: str, read: _Read, *, another: bool = True) -> None:
        """The car in the slot from `read` on. Locked.

        `another` False is the same car re-referenced - after our own off or
        stop moved its gap, or its handle back in the box: not news of a new
        car, only a new baseline."""
        if another:
            slot = (side, read.key)
            self._segment[slot] = self._segment.get(slot, 0) + 1
        self._key_ref[(side, read.key)] = read
        self._ref[side] = read
        self._run[side] = []
        self._refused[side] = 0
        self._band[side] = _band_index(read.gap_s)
        self._band_pending[side] = None

    def _follow(self, side: str, read: _Read) -> None:
        """The neighbour's handle read again: the same car, or not. Locked."""
        ref, run = self._ref[side], self._run[side]
        if run and continuous(run[-1].gap_s, run[-1].packet, read.gap_s,
                              read.packet):
            # The more recent chain first: a figure that fits both is the
            # figure the readings since the jump have been walking towards.
            run.append(read)
            if len(run) >= SUBJECT_HOLD_READS:
                self._another_car(side, ref, run)
            return
        if ref is None or continuous(ref.gap_s, ref.packet, read.gap_s,
                                     read.packet):
            if run:
                log("race").info(
                    "news: %d reading(s) of the car %s at %.2f s refused - "
                    "back to %.2f s, the car it was", len(run), side,
                    run[0].gap_s, read.gap_s)
            self._run[side] = []
            self._refused[side] = 0
            self._ref[side] = read
            self._key_ref[(side, read.key)] = read
            self._move_band(side, read.gap_s)
            return
        if not run:
            log("race").info(
                "news: the car %s went %.2f -> %.2f s in %.1f s, beyond %.1f s "
                "+ %.2f s/s - held until %d readings agree", side, ref.gap_s,
                read.gap_s, (read.packet - ref.packet) / SAMPLE_HZ,
                JUMP_NOISE_S, JUMP_RATE_S_PER_S, SUBJECT_HOLD_READS)
        self._run[side] = [read]
        self._refused[side] += 1
        if self._refused[side] >= RETIRE_AFTER_REFUSALS:
            # Rule 10. Nothing agrees with the car and nothing agrees with
            # anything else: the car is the reference that is wrong.
            log("race").warning(
                "news: %d readings of the car %s running fit neither %.2f s "
                "nor each other - that car is retired until %d agree",
                self._refused[side], side, ref.gap_s, NEIGHBOUR_HOLD_READS)
            self._neighbour[side] = None
            self._ref[side] = None
            self._run[side] = []
            self._refused[side] = 0

    def _another_car(self, side: str, ref: _Read, run: list) -> None:
        """Readings that broke from the car and agree: another car under the
        same handle. Locked."""
        key = ref.key
        before, after = ref.moment_before, run[-1].moment
        across = _explained(before, after)
        ours = _ours_between(before, after)
        for r in run:
            if r.lap_key is not None:
                self._broke_on.setdefault(key, set()).add(int(r.lap_key))
        if ours:
            # **Our own off or stop**: the same car's gap moves by what it
            # cost, and a place lost in it may or may not be a new car in the
            # slot. Explained; evidence of nothing about the handle.
            why = (f"our off or stop moved the {side} gap "
                   f"({ref.gap_s:.1f} -> {run[0].gap_s:.1f} s)")
        elif across:
            # **The same handle held the slot across a place change or a
            # rival's stop**: it names the slot, not a car. The figure is
            # still the box's, right about whoever is there now.
            why = (f"held the {side} slot across a place change or a stop "
                   f"({ref.gap_s:.1f} -> {run[0].gap_s:.1f} s)")
            if key not in self._merged:
                self._merged[key] = why
                log("race").warning(
                    "news: %s names a slot, not a car, this race - no name "
                    "and no pace off it: %s", key, why)
        else:
            self._jumps[key] = self._jumps.get(key, 0) + 1
            why = (f"{self._jumps[key]} jump(s) nothing on the circuit "
                   f"explains, latest {ref.gap_s:.1f} -> {run[0].gap_s:.1f} s")
            if (key not in self._unreliable
                    and self._jumps[key] >= UNRELIABLE_AFTER_JUMPS):
                self._unreliable[key] = why
                log("race").warning(
                    "news: %s's readings jump with nothing to explain it - "
                    "its gaps are said unconfirmed this race: %s", key, why)
        log("race").info("news: the car %s %s under %s at %.2f s "
                         "(%d readings agree; %s)", side,
                         "is the same car" if ours else "is another car",
                         key, run[-1].gap_s, len(run), why)
        self._new_car(side, run[-1], another=not ours)

    def _move_band(self, side: str, gap_s: float) -> None:
        """Across a band only past the dead band, on two readings running."""
        now = self._band[side]
        wanted = _band_index(gap_s, current=now)
        if wanted == now:
            self._band_pending[side] = None
            return
        pending = self._band_pending[side]
        if pending is not None and pending[0] == wanted:
            self._band[side] = wanted
            self._band_pending[side] = None
            return
        self._band_pending[side] = (wanted,)

    def note_board(self, rows, own_row: int | None, *, packet: int,
                   our_position: int | None) -> None:
        """One frame's board rows. Worker thread."""
        mapped = board_places(rows, own_row, our_position)
        if mapped is None:
            return
        places, visible, windowed = mapped
        read = BoardRead(packet=int(packet), places=places, visible=visible,
                         windowed=windowed)
        with self._lock:
            self._board_before, self._board = self._board, read

    def note_lap(self, lap_key: int, lap_num: int, lap_time_s: float | None,
                 dirty: str | None = None, *, lane=None) -> None:
        """A crossing: the lap the wall's readings under `lap_key` belong to.

        Qt thread. Files each neighbour's lap into `RivalPace` - his lap time
        from ours and the change in the gap - with the reason where the lap is
        not a lap of his pace or ours.
        """
        with self._lock:
            key = int(lap_key)
            if dirty:
                self._dirty.add(key)
            if lap_time_s:
                self._ours_s[key] = float(lap_time_s)
            for side in SIDES:
                trend = self._trends[side]
                seen = dict(trend.seen)
                subject = trend.subject
                if subject is None:
                    continue
                subject = str(subject)
                pace = self._pace[side]
                reason = dirty
                if reason is None and lane is not None:
                    reason = _in_the_lane(lane, subject, key)
                pace.note_lap(key, lap_time_s, seen.get(key),
                              seen.get(key - 1), ahead=(side == "ahead"),
                              subject=subject, exclude=reason)

    # ------------------------------------------------------------- the calls

    def gaps_call(self, state, now: int) -> Call | None:
        """The gap ahead and behind, when it matters.

        Said when the car ahead or behind changes, when a gap crosses a band
        (`BANDS_S`), or - at most once a lap - as a refresher while either car
        is inside `REFRESH_WITHIN_S`. Never with both cars far away unless one
        of them is new.
        """
        lap_key = state.lap_now()
        with self._lock:
            entries = []
            for side in SIDES:
                reads = self._reads[side]
                neighbour = self._neighbour[side]
                latest = self._ref[side]
                if not reads or neighbour is None or latest is None:
                    continue
                if (reads[-1] is not latest
                        or now - latest.packet > packets(GAP_FRESH_S)
                        or latest.gap_s <= 0):
                    # The newest reading is not the car's own: a jump held
                    # until readings agree, or another handle in the box.
                    continue
                identity = (neighbour,
                            self._segment.get((side, neighbour), 0))
                unsure = self._unreliable.get(neighbour)
                name = (None if unsure or neighbour in self._merged
                        else self._neighbour_name[side])
                said = self._said_gap[side]
                band = self._band[side]
                if said is not None and not _explained(
                        said[2].moment_before, latest.moment) and not continuous(
                        said[2].gap_s, said[2].packet, latest.gap_s,
                        latest.packet):
                    # **Never a jump he hears.** The last figure he was told
                    # on this side, and this one, are not one car's gap and
                    # nothing on the circuit put another car there. Silent
                    # until the figure is one the time since could explain
                    # - the envelope keeps widening (`DRIFT_S_PER_S`), so
                    # this retires itself (rule 10).
                    continue
                changed = said is None or said[0] != identity
                if (changed and latest.gap_s >= REFRESH_WITHIN_S
                        and a_person(name) is None):
                    # **A new unnamed car far away teaches him nothing.**
                    # Replayed at Bathurst the board's clusters handed the
                    # car behind to three unnamed cars in a minute during the
                    # stop cycle - "The car behind, 22 seconds.", "28
                    # seconds.", "14 seconds." - none of them racing him.
                    # A named one is still news: who is up the road is.
                    changed = False
                banded = (said is not None and said[0] == identity
                          and said[1] != band)
                entries.append((side, latest, identity, name, band,
                                changed, banded, unsure))
            refresher_due = self._gap_lap is None or lap_key > self._gap_lap
        if not entries:
            return None
        event = [e for e in entries if e[5] or e[6]]
        near = [e for e in entries if e[1].gap_s < REFRESH_WITHIN_S]
        if event:
            said = [e for e in entries if e in event or e in near]
            why = "; ".join(
                f"the car {e[0]} is {'new' if e[5] else 'across a band'}"
                for e in event)
        elif near and refresher_due:
            said = near
            why = "refresher, a car inside %.0f s" % REFRESH_WITHIN_S
        else:
            return None
        # **A handle whose readings jump with nothing to explain it is said
        # unconfirmed, not silenced** (`UNRELIABLE_AFTER_JUMPS`). The reader
        # is what is in doubt there, and "unconfirmed" is the word §5.5 gives
        # him to act on - he has the box on his own screen. A handle that
        # only held the slot across a place change is not in doubt about its
        # figure: that is the box, and every figure here is continuous with
        # the car in the slot or explained by what changed it. It loses its
        # name and its pace (`_merged`), not its number. Replayed at session
        # 176 with the word on those too, it was on 14 of 16 gap lines, each
        # continuous with its car or said across a pass - and a word on every
        # line is a word he stops hearing.
        # The unsure side goes last so the word follows the figure it
        # qualifies.
        said.sort(key=lambda e: e[7] is not None)
        unsure = [e for e in said if e[7] is not None]
        words = " ".join(gap_sentence(e[0], e[3], e[1].gap_s) for e in said)
        call = Call(GAPS, state.lap, words, "", LOW if unsure else MEDIUM,
                    why_spoken=f"{why}; GT7's interval boxes as read "
                               f"(0.1 s under {TENTHS_BELOW_S:.0f} s); "
                               "names from the roster; each figure "
                               "continuous with the car it is about"
                               + "".join(f"; the car {e[0]}'s handle "
                                         f"{e[2][0]} is unconfirmed: {e[7]}"
                                         for e in unsure))
        booked = {e[0]: (e[2], e[4], e[1]) for e in said}

        def book() -> None:
            with self._lock:
                self._said_gap.update(booked)
                self._gap_lap = lap_key
        return self._offer(call, book)

    def pace_call(self, state, now: int, *, lane=None) -> Call | None:
        """A pace difference to a neighbour that beat the noise. See
        `pace_verdict` for the test."""
        now_key = state.lap_now()
        with self._lock:
            trends = {side: replace(self._trends[side],
                                    seen=dict(self._trends[side].seen))
                      for side in SIDES}
            paces = {side: self._pace[side] for side in SIDES}
            ours = dict(self._ours_s)
            dirty = set(self._dirty)
            names = dict(self._neighbour_name)
            said = dict(self._said_pace)
            unreliable = {**self._merged, **self._unreliable}
            broke_on = {k: set(v) for k, v in self._broke_on.items()}
        for side in SIDES:
            trend = trends[side]
            if trend.subject is None:
                continue
            subject = str(trend.subject)
            if subject in unreliable:
                # **A rate is a claim about one car**, and this handle has
                # been more than one this race.
                continue
            his = _lane_keys(lane, subject, now_key) if lane is not None \
                else set()
            # A lap the handle changed car on is not a lap of either car.
            his |= broke_on.get(subject, set())
            verdict, why_not = pace_verdict(
                trend, side, paces[side], ours, now_key=now_key,
                dirty_keys=frozenset(dirty | his))
            if verdict is None:
                continue
            figure = round(abs(verdict.rate), 1)
            sign = verdict.rate > 0
            before = said.get(side)
            if before is not None and before[0] == subject \
                    and before[1] == sign:
                if (abs(figure - before[2]) < PACE_REPEAT_S_PER_LAP
                        or before[3] == now_key):
                    continue
            name = names.get(side) if names.get(side) and \
                str(names.get(side)) == subject else None
            named = a_person(name) is not None
            call = Call(
                PACE, state.lap, pace_sentence(side, name, verdict.rate),
                pace_reason(verdict.laps), MEDIUM if named else LOW,
                why_spoken=(
                    f"gap to the car {side}, lap keys {verdict.first_lap}-"
                    f"{verdict.last_lap}: his lap less ours "
                    f"{verdict.gain_s_per_lap:+.2f} s/lap, 95% interval "
                    f"+/-{verdict.half_width_s:.2f} over {verdict.changes} "
                    f"clean changes excludes zero; board rate "
                    f"{verdict.rate:+.2f} over {verdict.laps} laps"
                    + ("" if named else "; unnamed car - his stops cannot "
                       "be checked, so unconfirmed")),
                tag=f"{PACE}:{side}:{subject}")

            def book(side=side, entry=(subject, sign, figure, now_key)):
                with self._lock:
                    self._said_pace[side] = entry
            return self._offer(call, book)
        return None

    def watched_call(self, state, now: int) -> Call | None:
        """A championship rival's place, when it changes or after his stop."""
        watched = getattr(state, "watched_rivals", None) or frozenset()
        ours = state.position
        if not watched or not ours:
            return None
        with self._lock:
            board, before = self._board, self._board_before
        if board is None or now - board.packet > packets(BOARD_FRESH_S):
            return None
        for name, place in sorted(board.places.items(), key=lambda kv: kv[1]):
            lowered = name.lower()
            if lowered not in watched or place == ours:
                continue
            if before is None or before.places.get(name) != place:
                continue                                    # not held yet
            side = "ahead" if place < ours else "behind"
            lane = getattr(state, "lane", None)
            visits = lane.visits_by(name) if lane is not None else []
            if any(v.left_lap is None for v in visits):
                # Standing in his box: the one moment his place does not
                # describe where he is racing (`RaceState.rival_positions`).
                continue
            out = [v for v in visits if v.left_lap is not None
                   and v.key not in self._watch_stops_told]
            said = self._said_watch.get(lowered)
            if said is None and not out:
                # **The first sight is a baseline, not news.** Said on the
                # grid it would be three names in the first minute.
                # Booked as though said long ago, so the first real change
                # is not held back by the repeat interval.
                with self._lock:
                    self._said_watch[lowered] = (
                        place, side, now - packets(WATCHED_REPEAT_S))
                continue
            if said is not None and not out:
                moved = place != said[0]
                if not moved:
                    continue
                if side == said[1] and now - said[2] < packets(
                        WATCHED_REPEAT_S):
                    continue
            call = Call(
                WATCHED, state.lap, watched_sentence(name, place, ours),
                "After his stop." if out else "", MEDIUM,
                why_spoken=(
                    f"championship rival from the brief; P{place} off the "
                    f"board ({'top three and a window' if board.windowed else 'rows as places'})"
                    f" against our P{ours}"
                    + ("; first place seen since his stop" if out else "")),
                tag=f"{WATCHED}:{lowered}")
            keys = [v.key for v in out]

            def book(lowered=lowered, entry=(place, side, now), keys=keys):
                with self._lock:
                    self._said_watch[lowered] = entry
                    self._watch_stops_told.update(keys)
            return self._offer(call, book)
        return None

    def picture(self, state, now: int, *, required: int | None,
                required_source: str | None, planned: int,
                extra_dropped: int = 0) -> tuple | None:
        """`(line, confident, basis)` for the stop cycle, or None.

        `line` is `("still", k)` - k cars ahead of us on the road not yet
        seen stopping while we still owe ours - or `("effective", place)`,
        our place once every car still to stop has, on the assumption that
        each car stops `required` times.
        """
        position = state.position
        lane = getattr(state, "lane", None)
        if not position or lane is None or not required:
            return None
        if not lane.stops() and not extra_dropped:
            return None                         # the cycle has not begun
        ours_owed = max(0, max(int(required), int(planned or 0))
                        - int(state.stint_index))
        with self._lock:
            board = self._board
        fresh = board is not None and now - board.packet <= packets(
            BOARD_FRESH_S)
        if fresh:
            def owed(name):
                return max(0, int(required) - len(lane.visits_by(name)))
            ahead = [n for n, p in board.places.items() if p < position]
            behind = [n for n, p in board.places.items() if p > position]
            seen_ahead = len([p for p in board.visible if p < position])
            seen_behind = len([p for p in board.visible if p > position])
            everyone_ahead = seen_ahead >= position - 1
            still = [n for n in ahead if owed(n) > 0]
            if ours_owed > 0 and still:
                return (("still", len(still)), everyone_ahead,
                        f"{len(still)} of {len(ahead)} named cars ahead not "
                        f"seen stopping")
            place = (position
                     - sum(1 for n in ahead if owed(n) > ours_owed)
                     + sum(1 for n in behind if owed(n) < ours_owed))
            field = state.field_size
            everyone = everyone_ahead and (
                ours_owed == 0
                or (field is not None and seen_behind >= field - position))
            return (("effective", place), everyone,
                    f"board: {len(ahead)} named ahead, {len(behind)} behind, "
                    f"we owe {ours_owed}")
        if ours_owed == 0:
            return None
        dropped = len(lane.dropped_behind()) + int(extra_dropped)
        if dropped <= 0:
            return None
        return (("effective", position + dropped), False,
                f"lane only: {dropped} car(s) that were ahead boxed and are "
                f"behind on the road, we owe {ours_owed}; the board's picture "
                f"of the rest is not in hand")

    def picture_call(self, state, now: int, *, required: int | None,
                     required_source: str | None, planned: int,
                     extra_dropped: int = 0, position_called: int | None = None,
                     hold: bool = True) -> Call | None:
        """What the stops mean for us, when that has changed."""
        found = self.picture(state, now, required=required,
                             required_source=required_source,
                             planned=planned, extra_dropped=extra_dropped)
        if found is None:
            return None
        line, everyone, basis = found
        position = state.position
        with self._lock:
            said = self._said_picture
            if hold:
                pending = self._picture_pending
                if pending is None or pending[0] != line:
                    self._picture_pending = (line, now)
                    return None
                if now - pending[1] < packets(PICTURE_HOLD_S):
                    return None
        if line == said:
            return None
        if said is None and line == ("effective", position):
            return None                 # nothing changed by the stops yet
        confident = everyone and required_source == "the regulations"
        call, reason = picture_words(position, line, int(required))
        made = Call(
            STOPS_PICTURE, state.lap, call, reason,
            MEDIUM if confident else LOW,
            # **The road place it names, as a field**: booked as the place he
            # was told when it is heard, and what `call_outcome` holds it to.
            position_called=(position_called if position_called is not None
                             else position),
            why_spoken=(f"{basis}; each rival assumed to stop {required} "
                        f"time(s), from {required_source}"
                        + ("" if everyone else
                           "; the board does not show every car counted")),
            tag=f"{STOPS_PICTURE}:{line[0]}:{line[1]}")

        def book(line=line):
            with self._lock:
                self._said_picture = line
        return self._offer(made, book)

    # ------------------------------------------------------------ booking

    def _offer(self, call: Call, book) -> Call:
        with self._lock:
            if len(self._offers) > 32:
                self._offers.clear()
            self._offers[id(call)] = (call, book)
        return call

    def book(self, call) -> None:
        """Heard: what the call claimed becomes what he was told."""
        with self._lock:
            entry = self._offers.pop(id(call), None)
        if entry is not None and entry[0] is call:
            entry[1]()

    def release(self, call) -> None:
        """Not heard: nothing is booked, and the next offer is built fresh."""
        with self._lock:
            self._offers.pop(id(call), None)


# ------------------------------------------------------------------- helpers

def _agree(reads) -> bool:
    """Each reading continuous with the one before it."""
    return all(continuous(a.gap_s, a.packet, b.gap_s, b.packet)
               for a, b in zip(reads, reads[1:]))


def _band_index(gap_s: float, current: int | None = None) -> int:
    """Which band a gap is in, with the dead band either side of each edge
    where `current` is known."""
    if current is None:
        return sum(1 for edge in BANDS_S if gap_s >= edge)
    band = current
    while band > 0 and gap_s <= BANDS_S[band - 1] - BAND_HYSTERESIS_S:
        band -= 1
    while band < len(BANDS_S) and gap_s >= BANDS_S[band] + BAND_HYSTERESIS_S:
        band += 1
    return band


def _lane_keys(lane, driver: str, now_key: int) -> set[int]:
    """The lap keys a car was in the lane for, and the lap out of it."""
    keys: set[int] = set()
    for visit in lane.visits_by(driver) if lane is not None else ():
        start = visit.lap if visit.lap is not None else visit.noted_lap
        end = visit.left_lap if visit.left_lap is not None else now_key
        keys.update(range(int(start), int(end) + 2))
    return keys


def _in_the_lane(lane, driver: str, key: int) -> str | None:
    if key in _lane_keys(lane, driver, key):
        return "he was in the lane on this lap"
    return None
