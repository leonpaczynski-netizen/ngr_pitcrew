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
* **a place is the board's LAST ACCEPTED read, or the row has none.** Not the
  accumulated `rival_positions`, which is updated once a lap and never pruned:
  merging it under one age put a name read twenty laps ago beside a live one,
  two cars at the same place, and a retired car still holding P7;
* **a gap exists only for the two cars either side of us**, because only they
  have an interval box on his screen - and it is attached by the trend's own
  `subject`, never by "whoever the board last put at `ours ± 1`". It expires
  - `gap_still_stands`, on the lap it was read and on whether the board
  reader is still reading - because a reading that cannot go stale is one
  that sits on screen after the reader has stopped, and a gap he has already
  driven past is worse than no gap. A gap that has expired is drawn as
  MISSING, not as an empty cell;
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
used. A car inside `SAVEABLE_FRACTION` may drive it out rather than stopping -
but that fraction is a QUARTER of the remaining fuel, so the row says what the
voice says, *"lifts or stops again"*, and carries no total for his race. The
screen does not get to assert what the voice refuses to (rule 13).

**Every lap number on this screen is a HUD number**, through
`calls.as_his_hud_numbers_it`. There are three domains in play - the app's
`state.lap`, GT7's drop-corrected `lap_now()` that the pit wall files a stop
against, and the HUD's lap-in-progress - and a first attempt here applied OUR
`laps_missed()` to a rival's stop lap, which `lap_now()` had already
corrected. It was right only in a race that lost no crossings.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from pitcrew.diagnostics import log
from pitcrew.race.calls import as_his_hud_numbers_it
from pitcrew.race.news import BOARD_FRESH_S, SAMPLE_HZ
from pitcrew.race.rival_calls import (
    Rival,
    _snapshot,
    fuel_shortfall,
    must_stop_again,
)

# The prediction, as the tablet words it. Each is a claim of a different
# strength, and they are kept apart for that reason (rule 13).
REACHES_FLAG = "reaches the flag"
SHORT_SAVES = "short - can save it"
STOPS_AGAIN = "stops again"
NO_STOP_SEEN = "no stop seen"
CANNOT_TELL = "can't tell"

# How old a board read may be before the places are marked as a moment behind
# is `news.BOARD_FRESH_S`, imported above and NOT a second copy of the name.
# This file declared its own at 6.0 against the 12.0 George refuses a board
# at, so between the two the tablet called a read stale while the voice was
# still building "2 ahead still to stop" from it, and past 12 the voice
# refused the board outright while the tablet kept drawing its places under
# an amber caption. One name, one value, one question - rule 13, applied to
# the code rather than to the words.

# How many of OUR laps a gap reading may be behind before the row stops
# carrying it. The trend is keyed by lap, not by packet, so the lap is the
# finest age a reading here HAS.
#
# **0, and it used to be 1 against a lap counted one lower.** `GapTrend` is
# keyed by `RaceState.lap_now()` - the laps BEHIND him - and this file counts
# in `lap_on_screen()`, the lap in progress, which is one more. So
# `lap_on_screen - read_key > 1` was really "older than the lap he is
# driving", and the comment beside it said "a reading from the lap before is
# still drawn" - which it never was. Two lap domains in one subtraction is
# rule 13 in arithmetic: `as_his_hud_numbers_it` is the project's one
# conversion between them, this file already uses it for a rival's stop lap,
# and it is used here now so the constant means what it says.
#
# **The value is unchanged in effect: a gap is drawn only while it was read
# on the lap he is driving.** Measured on session 204 (2,659 readings) that
# refuses the figure 8-13% of the time, and what it draws is at most one lap
# old instead of the two `E-boards` feared.
GAP_STALE_LAPS = 0


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
    # **How many of his stops that burn rests on** (rule 4). One stop is one
    # stint's worth of evidence about a driver who may have been saving, and
    # the row said "his burn" identically whether it stood on one or on six.
    # None where the burn is ours - our own burn is this race's, measured over
    # every lap of it, and a count there would invite a comparison between two
    # different kinds of number.
    burn_stops: int | None = None
    # The shortfall is inside what two readings and a burn can resolve.
    unconfirmed: bool = False
    # **Fuel beyond the flag, and whether we can read it.** "Reaches the
    # flag" was one verdict for two very different cars: one with ten litres
    # to spare, free to push, and one with two - Rocky at Sardegna Rd 9, who
    # had to hold his rate for the whole stint and told the driver so. The
    # difference is whether the spare is bigger than the reading error
    # (`Shortfall.error_l`), so there is no new threshold here to tune.
    spare_l: float | None = None
    spare_readable: bool = False
    # **`stops_seen` is a floor, not a count** - the lane only sees the cars
    # GT7 draws, and `max(seen, 1)` raises it from the pit flag. So a total
    # built on it is a lower bound too, and says so rather than reading as a
    # tally of his race.
    seen_is_a_floor: bool = True


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
    # The entry figure is an UPPER bound: the wall joined the fill running.
    in_is_bound: bool = False
    # **A gap for this car exists and is too old to stand behind.** Not the
    # same as `gap_s is None`, which is "no gap was ever read against this
    # car" - a car that is not one of the two either side of us has no
    # interval box at all and never will. The driver has to be able to tell
    # "the reader has lost the number" from "there is no number to have", and
    # an empty cell says both (rule 3).
    gap_unread: bool = False
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
    # Whether that distance is the plan's estimate rather than a count.
    laps_total_hedged: bool = False
    why: str | None = None


def gap_still_stands(read_key: int | None, lap_on_screen: int | None,
                     board_age_s: float | None) -> bool:
    """Whether a gap reading may still be drawn as THE gap. One expression.

    A gap is the one number on this screen he acts on at racing speed, and it
    is the only one the page could not age: `latest()` is keyed by lap and
    never expires, so a reader that stopped left a bare "1.4" up. *"A gap
    that is 8 seconds stale under braking is worse than no gap"* - he passes
    the car and the number still describes the one he passed.

    **Two conditions, one question - "is this reading still the gap?"** They
    are not two ideas of staleness bolted together; they are the two ways the
    same instrument goes quiet, and neither sees the other's case:

    * **It was read on the lap he is driving** (`GAP_STALE_LAPS`). The trend
      is keyed by lap and nothing finer is recorded, so this is the only
      bound that can catch a reading from *before* the crossing. `read_key`
      is a `lap_now()` key - laps behind him - and `lap_on_screen` is the lap
      in progress, so the key is converted with `as_his_hud_numbers_it`
      rather than the two being subtracted in different domains.
    * **The board - the same instrument, the same frames - has been read
      inside `BOARD_FRESH_S`.** The pit wall reads the ladder and the interval
      boxes off one frame in one pass, and it is measurable how tightly the
      two travel: of the gap readings the tablet can draw (a subject the
      roster named), **2054 of 2057 at session 204, 1507 of 1507 at 188 and
      771 of 771 at 176 came off a frame that also produced a board read** -
      99.9%, 100%, 100%. So a board that has gone quiet is a reader that has
      stopped, and a gap it left behind is not a current reading whatever lap
      it was taken on. This is `news.BOARD_FRESH_S`, the value George already
      refuses a board at and the one the header already counts against: one
      name, one value, one question (rule 13).

    **Why a cut in seconds is needed at all, measured.** On session 204 the
    board reader ran at a median 1.28 s (ahead) / 1.15 s (behind) between
    readings, p95 8.3 / 8.6 s, p99 14.1 / 17.5 s. A gap that has not been
    re-read for twelve seconds is therefore not a slow reader, it is a
    stopped one - about one reading in a hundred. Replaying the stored
    readings through both conditions against the lap bound alone: the oldest
    figure drawn falls from **83 s to 31 s (ahead) and 46 s (behind)**, the
    share of the race drawing a figure over 30 s old from 2.0%/4.1% to
    0.1%/0.9%, and over 12 s old from 13.0%/16.5% to 4.5%/7.7%. It costs
    refusing the figure 22.8%/26.3% of the time against 15.2%/18.5%. That
    replay stands a board read in for by the only trace of one the archive
    keeps - a gap reading that carried our own place, which is what
    `_on_board` is gated on - so it is indicative rather than exact: it
    misses board reads taken on frames with no interval box, and counts
    frames whose rows `news.board_places` went on to refuse.

    **An age that cannot be established is not an age of zero** (rule 3).
    No lap, no read key, or no board read at all, and the reading does not
    stand - it is drawn as unread rather than as a number.
    """
    read_lap = as_his_hud_numbers_it(read_key)
    if read_lap is None or lap_on_screen is None:
        return False
    if lap_on_screen - read_lap > GAP_STALE_LAPS:
        return False
    return board_age_s is not None and board_age_s <= BOARD_FRESH_S


def predict(rival: Rival | None, *, stops_seen: int, our_burn_l: float | None,
            laps_total: int | None) -> Prediction:
    """The stop picture for one car, from `fuel_shortfall` and nothing else."""
    if rival is None or rival.stop is None:
        return Prediction(stops_seen=stops_seen,
                          words=NO_STOP_SEEN if stops_seen == 0 else CANNOT_TELL,
                          why=None if stops_seen == 0 else "no fuel read at his stop")
    burn_of = "his" if rival.burn_per_lap_l else "ours"
    stops = getattr(rival, "burn_stops", 0) or None
    evidence = stops if burn_of == "his" else None
    if rival.exit_is_a_bound:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="exit fuel a lower bound",
                          burn_of=burn_of)
    if laps_total is None:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="no race length", burn_of=burn_of)
    short = fuel_shortfall(rival, our_burn_l, laps_total=laps_total)
    if short is None:
        return Prediction(stops_seen=stops_seen, words=CANNOT_TELL,
                          why="no fuel or burn read", burn_of=burn_of)
    # **`must_stop_again` decides, here and in the voice.** The branch used
    # to be re-derived from `short` in both places, so the row and
    # `news.picture` could answer "will he stop again" two ways about one car
    # from one state (rule 13).
    verdict = must_stop_again(rival, our_burn_l, laps_total=laps_total)
    if verdict is False:
        spare = -short.litres
        return Prediction(stops_seen=stops_seen, words=REACHES_FLAG,
                          total_stops=stops_seen, burn_of=burn_of,
                          burn_stops=evidence,
                          unconfirmed=not short.certain,
                          spare_l=spare,
                          spare_readable=spare > short.error_l)
    if verdict is None:
        # **`total_stops=None`, because the app does not know.**
        # `short_to_the_flag` says this same shortfall as "he lifts OR he
        # stops again" and its docstring is explicit that asserting either
        # half is the defect it was written to fix - and the threshold here
        # is a QUARTER of the remaining fuel, not "a few per cent". The row
        # said "1 STOP / short, saves it" while George said he might come in,
        # about one car, from one set of numbers.
        return Prediction(stops_seen=stops_seen, words=SHORT_SAVES,
                          total_stops=None, burn_of=burn_of,
                          burn_stops=evidence,
                          unconfirmed=not short.certain)
    burn = rival.burn_per_lap_l or our_burn_l
    reaches = rival.stop.lap + int(rival.stop.fuel_out_l / burn)
    return Prediction(stops_seen=stops_seen, words=STOPS_AGAIN,
                      total_stops=stops_seen + 1, reaches_lap=reaches,
                      burn_of=burn_of, burn_stops=evidence,
                      unconfirmed=not short.certain)


def _on_his_hud(prediction: Prediction) -> Prediction:
    """The lap a prediction names, as his HUD will number it.

    `reaches_lap` is built from `rival.stop.lap`, which the pit wall files in
    our own COMPLETED-lap count - the same domain `must_stop_by` speaks in.
    One conversion, `calls.as_his_hud_numbers_it`, so the row and the voice
    cannot name two different laps for one car.
    """
    if prediction.reaches_lap is None:
        return prediction
    return replace(prediction,
                   reaches_lap=as_his_hud_numbers_it(prediction.reaches_lap))


def field_view(state, board, *, packet: int | None) -> FieldView:
    """Everyone the app knows about, as of now.

    `board` is `RaceNews.board()` - the last board read, as places by name -
    or None. Pure: given a race state and a board, so it tests without a race.
    """
    if state is None:
        return FieldView(why="no race running")
    ours = getattr(state, "position", None)
    # **Every lap number here is the one his HUD shows.** `state.lap` is the
    # app's count of completed laps and the two drift apart - a crossing lost
    # in the pit lane put Road Atlanta +1 on lap 1 and +2 by lap 20 - so a
    # tablet counting in the app's domain would disagree with the phone a foot
    # away, with the HUD, and with George. `lap_on_screen` is the one
    # expression for OUR lap.
    #
    # **A rival's stop lap is a different conversion, and it was the wrong
    # one.** This used to add `lap_on_screen() - lap - 1` - which is
    # `laps_missed()` - to a figure the pit wall had ALREADY drop-corrected,
    # so the row was a lap early in a clean race and drifted further in a
    # dirty one. `as_his_hud_numbers_it` is the conversion, and `must_stop_by`
    # now speaks through the same one.
    on_screen = getattr(state, "lap_on_screen", None)
    lap_now = on_screen() if callable(on_screen) else getattr(state, "lap", None)
    base = dict(position=ours, field_size=getattr(state, "field_size", None),
                lap=lap_now,
                laps_total=getattr(state, "laps_total", None),
                # **In a timed race the distance is an ESTIMATE**, and every
                # spoken call says "about" for it. The header printed a flat
                # "/ 30" and every prediction on the screen rests on it
                # (`fuel_shortfall` divides by laps-to-flag), so the hedge
                # belongs here too or the screen is the confident one (rule 5).
                laps_total_hedged=bool(
                    getattr(state, "laps_count_hedged", False)))
    lane = getattr(state, "lane", None)
    rivals = dict(getattr(state, "rivals", None) or {})
    our_burn = getattr(state, "fuel_per_lap_l", None)
    laps_total = base["laps_total"]

    # **A place is the board's, or the row has none.** This used to start
    # from `state.rival_positions` - which the coordinator `update()`s once a
    # lap and NEVER prunes - and merge the board over it, so a name read at
    # P5 twenty laps ago kept that row for the rest of the race, sitting next
    # to a live one under one caption that said how old the BOARD was. Two
    # cars at P5, and a P7 that retired ten laps back, all reading as current.
    #
    # A rival we hold no fresh place for still gets his row: the stop and the
    # fuel are facts about a stop that happened, and they do not go stale the
    # way a position does. He sorts to the bottom with no place shown, which
    # is what a car whose row was never read has always done here.
    places: dict[str, int] = {}
    age = None
    if board is not None:
        if packet is not None:
            seconds = (int(packet) - int(board.packet)) / SAMPLE_HZ
            # **A negative age is a refusal, not a zero** (rule 9). The packet
            # counter resets at the arm while the wall's thread is mid-read,
            # and a read stamped against the last race clamped to "0 s ago"
            # would put the PREVIOUS race's places on screen as current.
            if seconds < 0:
                # **And its PLACES are refused with it, which they were not.**
                # The guard took the age and kept the data, so the page said
                # "board not read yet" while drawing a full timing tower - of
                # the previous race, whose order it had carried over. A page
                # that hedges in one corner and asserts in the middle is
                # worse than either half alone.
                log("race").warning(
                    "the tablet's board read is stamped %.0f s ahead of the "
                    "packet count - refused, places and all, rather than "
                    "shown as fresh", -seconds)
            else:
                age = seconds
                places.update(board.places)
        else:
            # No packet count to age it against: the read cannot be shown as
            # fresh, so it is not shown as a place at all.
            log("race").info("the tablet has a board read with no packet "
                             "count to age it - places refused")
    # **"IN LANE" is the one thing on this screen happening RIGHT NOW, and it
    # could not expire.** `in_the_lane()` is every visit whose exit was never
    # filed, and only `note_rival_stop` clears one - which returns early when
    # the race is not running, among other gates. So a visit the wall never
    # closed kept the amber plate up for the rest of the race, saying a car
    # was standing in its box twenty laps after it left. `untold()` has
    # `STALE_AFTER_LAPS` for exactly this; the plate had nothing.
    from pitcrew.race.lane import STALE_AFTER_LAPS

    standing = set()
    for stop in (lane.in_the_lane() if lane is not None else []):
        began = getattr(stop, "lap", None)
        our_lap = getattr(state, "lap", None)
        if (began is not None and our_lap is not None
                and our_lap - began > STALE_AFTER_LAPS):
            continue                 # nobody stands in a box for three laps
        standing.add(str(stop.driver).lower())

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
            last_stop_lap=as_his_hud_numbers_it(getattr(stop, "lap", None)),
            fuel_in_l=getattr(stop, "fuel_in_l", None),
            fuel_out_l=getattr(stop, "fuel_out_l", None),
            out_is_bound=bool(getattr(rival, "exit_is_a_bound", False)),
            in_is_bound=bool(getattr(rival, "entry_is_a_bound", False)),
            prediction=_on_his_hud(
                predict(rival, stops_seen=seen, our_burn_l=our_burn,
                        laps_total=laps_total))))
    if ours:
        # **A gap belongs to the car it was read against, by NAME.**
        # This used to pin it to whoever the board last put at `ours ± 1`,
        # discarding `GapTrend.subject` - which exists because the trend was
        # on file reporting confident numbers about a car that was no longer
        # there, and which every other reader carries (`_gap_view` prints the
        # name with the figure; `closing_call` tags per driver). Pass a car
        # into the last corner and the board is a few seconds behind: the row
        # for the car you just passed took the gap to the car you are now
        # chasing.
        by_name: dict[str, float] = {}
        # The cars a gap was read against and is no longer current for - see
        # `Car.gap_unread`. Kept apart from `by_name` so a car both sides
        # somehow name keeps the reading that still stands.
        unread: set[str] = set()
        for side, step in (("ahead", -1), ("behind", 1)):
            # **Snapshotted, because the wall's thread rebinds it.**
            # `GapTrend.latest` loads `seen` twice and `_rederive` rebinds it
            # between the two - `rival_calls._snapshot` exists for this and
            # says "Reproduced.", and `controller._gap_view` takes one. This
            # was the only reader that did not.
            trend = _snapshot(getattr(state, f"gap_{side}", None))
            seconds = trend.latest() if trend is not None else None
            if seconds is None:
                continue
            # **The roster's NAME for the trend's subject, because the rows
            # are named.** `GapTrend.subject` is a roster CLUSTER ID - an
            # int, straight out of `Roster.see_frame` via `pit_wall._neighbour`
            # - and it was compared against `row.name`, so `str(277).lower()`
            # matched no row, ever, and the tablet drew no gap for a whole
            # race (20 Sep, Bathurst Rd8). `gap_{side}_name` is
            # `roster.name_of(trend.subject)`, set in the same call as the
            # trend itself (`controller.note_gaps`), so this is the SAME
            # subject spelled the way the rows are - not "whoever the board
            # put at ours ± 1", which is the defect the comment above
            # describes. `controller._gap_view` asks the question this way
            # too, and rule 13 says the two surfaces may not have two
            # expressions for "whose gap is this".
            who = getattr(state, f"gap_{side}_name", None)
            # **No name, no gap.** The figure is real but the app cannot say
            # whose it is, and a number against the wrong row is worse than
            # no number - it is the shape of the mistake, not its size. An
            # unlabelled cluster has no name, so a gap read against one is
            # not drawn: on the Bathurst race that is about a third of the
            # readings, and drawing them would mean inventing a row for them.
            if who is None:
                # **`debug`, because this fires on about a third of the
                # readings and this function runs four times a second.** At
                # `info` that is up to eight lines a second for a whole race
                # - roughly thirty thousand of them - in the log the race is
                # read back from. It was harmless while `who` was a cluster
                # id and could never be None; it is not now. The screen is
                # where this refusal has to show, and it does: the row keeps
                # its place, its stop and its fuel, and draws no gap.
                log("race").debug(
                    "the tablet has a gap %s the roster has not named - not "
                    "drawn against a row", side)
                continue
            # **And it goes stale like every other reading** -
            # `gap_still_stands` is the whole of that judgement, and it is
            # one expression so the bound cannot be stated twice.
            read_on = max(trend.seen) if getattr(trend, "seen", None) else None
            if gap_still_stands(read_on, lap_now, age):
                by_name[str(who).lower()] = seconds
            else:
                # **Refused, and the row says so.** Dropping it silently left
                # an empty cell, which is what a car with no interval box at
                # all draws - so "the reader has lost the number" and "there
                # is no number to have" were one appearance.
                unread.add(str(who).lower())
        unread -= set(by_name)
        rows = [replace(row, gap_s=by_name[str(row.name).lower()])
                if str(row.name).lower() in by_name
                else replace(row, gap_unread=True)
                if str(row.name).lower() in unread
                else row
                for row in rows]
        rows.append(Car(name=None, place=int(ours), us=True))
    # By place; a car with no place (his stop was read, his row never was)
    # goes to the bottom rather than being given one.
    rows.sort(key=lambda row: (row.place is None, row.place or 0,
                               str(row.name or "")))
    return FieldView(rows=tuple(rows), board_age_s=age, **base)
