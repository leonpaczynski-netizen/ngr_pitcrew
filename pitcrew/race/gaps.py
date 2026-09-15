"""What the three gap readouts are worth: where a stop puts you, and closing rate.

GT7 publishes three intervals and no others - to the car ahead, to the leader,
to the car behind. This is what can be built on them, and it is the largest
thing the engineer was missing: **where you come out**.

### The rejoin is the call, and it dominates everything else here

A stop costs the fill plus the lane, and both are known exactly. At Spa on a
twelfth-lap stop that is 60 L at 1.0 L/s plus a measured pit loss - call it 80
seconds - against a lap of about 140. **Every car currently within that 80
seconds behind you emerges in front of you.** `gap_behind` is on the screen and
our own loss comes out of the plan, so the call is one subtraction:

    "Box now and you come out behind Rocky. He is 40 seconds back and the stop
     costs 80."

A place is worth far more than the whole overcut argument, which - once its
arithmetic was corrected - is worth a fraction of a second a lap.
`rivals.deferring_costs_s` carries that account.

### Closing rate, and what it is actually worth

**An earlier version of this file had the argument backwards and it is worth
recording which way round it goes.** It claimed a difference of gaps was
quieter than a lap-time comparison because the noise is common-mode and
cancels. The 0.918 s figure is this driver's own execution scatter - his
braking points, his small mistakes - which is idiosyncratic by definition and
is exactly what does NOT cancel. What genuinely is common between two cars -
track evolution, fuel-load trend, weather, rubbering-in - is slow and
systematic and contributes almost nothing to lap-to-lap scatter in the first
place.

What a gap difference removes is systematic DRIFT. It leaves all of the
execution scatter, from both cars. And because a gap is the cumulative sum of
per-lap differences it is a random walk, so a slope fitted to five of them has
a standard deviation near 0.5 s a lap - see `TREND_WORTH_SAYING_S`, which is
set from that number rather than from an intuition about traffic.

Traffic does not cancel either: two cars 5-40 s apart meet the same backmarker
on different laps. One lapped car costing him 1.5 s and the rival 0.2 s puts a
1.3 s step into a five-lap window, which is 0.26 s/lap of slope on its own.

### 5 Sep 2026 - a live gap now reads, and here is what it is worth

**For a fortnight the gap boxes were empty in every frame of footage
available.** Measured over a whole 48-minute Spa replay, every gap readout on
every frame showed `--:--.---`, because a replay does not draw them. So nothing
in this file had ever been given a real number, `read_gaps` returned `(None,
None)` on every frame ever tried, and the note that stood here said so.

The 4 Sep Daytona race capture does draw them. Three faults were in the way and
all three are fixed - `board.gap_lines` framed the box on the ink's own edge so
the clipped-box guard refused it before any reading began, `hud_time` read the
sign as punctuation, and the digit bank was built from pit-lane fuel figures at
twice the scale. `telemetry/smallfont.py` carries the new bank and the counts.

**What that is worth, honestly.** On 100 frames the reader had never seen, it
returns a value on 109 of 116 cleanly framed boxes and refuses the rest; two
readings differ from a hand transcription by one millisecond digit; no box
carrying no value read as a value. Sampled every five seconds across a race it
tracks a gap closing from 8.7 s to 0.2 s in tenths, and the only steps larger
than a second are overtakes - where both readouts flip on the same frame.

So the arithmetic below can now be fed. It still should not be believed further
than the reading: an unread gap is `None`, `GapTrend` needs five CONSECUTIVE
laps before it will quote a slope, and about a third of frames give no reading
at all because the box is framed with scenery in it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from pitcrew.strategy.model import (PIT_DEAD_TIME_S, PIT_LOSS_MEASURED,
                                    PIT_LOSS_MEASURED_EX_FUEL)
from pitcrew.telemetry.board import gap_lines
from pitcrew.telemetry.hud_time import read_gap

# Below this many seconds of difference, "you come out ahead of him" is a claim
# the arithmetic cannot support: the pit loss itself is only known to about a
# second, and a rival's own next lap moves the gap by more than that.
REJOIN_MARGIN_S = 3.0

# Laps of gap history before a closing rate is worth quoting. Three points is a
# slope through noise; five is a trend.
MIN_LAPS_FOR_TREND = 5

# Seconds a lap below which a closing rate is not worth saying.
#
# **0.15 was wrong by a factor of five, and the reason is that a gap is a
# random walk.** It is not a noisy measurement of a pace difference - it is the
# cumulative SUM of per-lap pace differences, so fitting a line to it and
# judging the slope against an iid-sized threshold is spurious regression.
# With this driver's 0.918 s lap-to-lap sigma and the five-point window here,
# the standard deviation of the returned slope is about 0.47-0.66 s/lap
# depending on how much of the two cars' noise is common. Simulated against
# this class, a threshold of 0.15 fired on **68-82% of five-lap windows where
# the two cars had identical pace.**
#
# Lengthening the window barely helps, which is the signature of the walk: for
# iid noise the slope's sd falls as n^-1.5, here it falls as n^-0.5. Twenty
# laps still gives a coin flip at 0.15.
#
# 0.8 is one and a half standard deviations at the middle of that range. It
# will miss real trends; that is the correct direction, because the failure it
# replaces was telling the driver he was catching somebody three times in four
# when nothing was happening.
#
# **Checked against the reader's own noise, 14 Sep 2026, and it stands.**
# Measured off `gap_reads` for sessions 143, 160, 166 and 176 (3,575 readings):
#
# * the READING is not what is noisy. Two readings of one car under 4 s apart
#   differ by a median 0.03-0.11 s (90th percentile 0.13-0.37 s), which is
#   the digit reader plus a few seconds of real racing;
# * the per-LAP value is. `seen` keeps the last reading of a lap, taken at a
#   different point on the road every lap, and adjacent laps of one car
#   differ with a standard deviation of 0.74-2.47 s (pooled 1.92 s, n=51) -
#   the random walk above, plus where on the lap the board happened to be
#   legible;
# * the rate this file quotes, over five consecutive laps of one car, came
#   out with a spread of 0.48-0.62 s a lap at session 143 - the band the
#   simulation above predicted. At session 176 it spread 1.7 s a lap, and
#   that session's "one car ahead" held through a climb from P11 to P7,
#   which is a board cluster standing for several drivers, not noise in a
#   gap.
#
# So 0.8 remains about one and a half standard deviations of what a real
# window produces with nothing happening, and the five laps stay. Letting a
# misread erase the history (fixed in `GapTrend.note`) was what kept the call
# unreachable; the threshold was not.
TREND_WORTH_SAYING_S = 0.8


@dataclass(frozen=True)
class TrendWords:
    """What a gap trend says about one side, for the eye and for the ear."""
    # The board's note, short: "catching 0.9 s a lap".
    board: str
    # The voice's clause, spelled out: "you're catching him 0.9 seconds a lap".
    spoken: str
    # Which way the news cuts, for the board's ink.
    urgent: bool
    good: bool


def trend_words(side: str, rate: float | None,
                laps: int | None) -> TrendWords | None:
    """The closing rate in words for `side`, or None - "steady".

    **One expression for the board and the voice** (rules 12 and 13, 11 Sep
    2026). The board applied this floor and these five laps; the push-to-talk
    answer said "closing" above 0.1 s a lap with no lap count at all, so the
    ear could say "closing 0.3 seconds a lap" while the eye read "steady"
    about the same car. None covers all three reasons there is nothing worth
    saying - no rate, too few consecutive laps, or a rate inside the noise -
    which is what "steady" has always meant on the board.

    **Written per side and never shared**, because one signed rate means
    opposite things: on the car ahead a closing gap is us catching him, on
    the car behind it is him catching us, and those demand opposite driving.
    """
    if rate is None or laps is None or laps < MIN_LAPS_FOR_TREND \
            or abs(rate) < TREND_WORTH_SAYING_S:
        return None
    pace = abs(rate)
    closing = rate > 0
    if side == "ahead":
        # Closing on the car ahead is the good news, and the one worth
        # spending tyre on.
        if closing:
            return TrendWords(f"catching {pace:.1f} s a lap",
                              f"you're catching him {pace:.1f} seconds a lap",
                              urgent=False, good=True)
        return TrendWords(f"losing {pace:.1f} s a lap",
                          f"you're losing {pace:.1f} seconds a lap to him",
                          urgent=True, good=False)
    # Behind, a closing gap is HIM catching US. Same number, opposite
    # instruction - which is the whole reason these are two sentences.
    if closing:
        return TrendWords(f"he is catching {pace:.1f} s a lap",
                          f"he's catching you {pace:.1f} seconds a lap",
                          urgent=True, good=False)
    return TrendWords(f"pulling away {pace:.1f} s a lap",
                      f"you're pulling away {pace:.1f} seconds a lap",
                      urgent=False, good=True)


def read_gaps(frame, board) -> tuple[float | None, float | None]:
    """`(ahead, behind)` in seconds, from the two rows either side of ours.

    **The boxes come from `board.gap_lines`, which has seen them.** This module
    used to carry its own band - `x1 - 1.6h` to `x1 + 1.4h` - written in the
    voice of a measurement and never measured, because no frame of available
    footage draws a gap at all. Two things were wrong with it. It disagreed
    with `gap_lines`, which was tuned against real frames and searches the
    row's own width rather than a narrower band shifted right into the flag and
    compound-disc columns. And it was too narrow: swept across a `1:23.456`,
    eleven pixel offsets of 121 returned a well-formed WRONG answer - `3.456`
    against a true 83.456 - which `rejoin_against` would then turn into a
    confident call about a car eighty seconds away from where it is.

    `hud_time` now refuses a box whose ink touches either edge, so a clipped
    read is a refusal rather than a shorter time. That guard and this one are
    both needed: one stops the band being wrong, the other stops a wrong band
    being believed.

    ### 5 Sep 2026 - it reads now, and the sign is what makes it safe

    Everything above described a function that had never returned a number.
    Three faults, all measured on the 4 Sep race capture and all now fixed
    elsewhere: `gap_lines` framed the box on the ink's own bounding edge so the
    clipped-box guard refused it before any reading began; the leading `+` fell
    through `hud_time`'s height test and came out as a `:`; and the digit bank
    was built from pit-lane fuel figures at twice the scale.

    **What is enforced HERE is that the sign matches the side.** The box above
    the driver's row is the car ahead and GT7 draws it `+`; the box below is
    the car behind and it draws it `-`. Measured on 169 boxes the two agree on
    every one that carries a sign. A disagreement means the box is not the box
    this function thinks it is - a mis-anchored row, a board found in the
    scenery - and that is a reading whose value would be confidently attached
    to the wrong car, which `GapTrend` is built entirely around not doing.

    `None` for either where the box carries no value: at the start of a race,
    for a car with nobody ahead of it, and on every frame of a replay, because
    a replay draws `--:--.---`.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3 or board is None:
        return None, None
    row = getattr(board, "row", board)
    try:
        ahead_box, behind_box = gap_lines(frame, row)
    except Exception:
        return None, None
    out = []
    for box, wanted in ((ahead_box, "+"), (behind_box, "-")):
        if box is None:
            out.append(None)
            continue
        x0, y0, x1, y1 = box
        patch = frame[y0:y1 + 1, x0:x1 + 1]
        got = read_gap(patch) if patch.size else None
        out.append(got[1] if got and got[0] == wanted else None)
    return out[0], out[1]


@dataclass(frozen=True)
class Rejoin:
    """Where a stop taken now would put us, relative to one car.

    `ahead` is `None` where it cannot be told - which includes the case where
    the two are close enough that the arithmetic does not separate them, and
    that is a real answer rather than a missing one.
    """
    ours_lost_s: float
    their_gap_s: float
    ahead: bool | None
    margin_s: float

    @property
    def too_close(self) -> bool:
        return self.ahead is None


def stop_costs_s(litres: float | None, refuel_rate_lps: float | None,
                 pit_loss_s: float | None,
                 pit_loss_source: str | None = None) -> float | None:
    """Total time a stop costs: the fill, plus the lane.

    **The dead time is in a declared pit loss and not in a measured one**, so
    the source has to travel with the figure. `strategy.model.stop_overhead_s`
    already gates on exactly this, and its docstring records the eight-second
    Monza over-estimate that forced the gate; this function took a bare float
    and could not apply it. With `REJOIN_MARGIN_S` at 3 s, a 7.5 s error flips
    the rejoin verdict outright for any rival in that window - so the same
    figure reached the driver from two expressions that disagreed, which is
    CLAUDE.md rule 12.

    **And only to a loss that EXCLUDES it.** `PIT_LOSS_MEASURED_EX_FUEL` is
    the whole stop less the refuelling - `race/pit_loss.py`'s figure, the one
    the event page stores as measured - and the dead time is already in it.
    Adding it there priced Bathurst's 23.13 s as 30.6 s and told him "A stop
    now puts you behind the car behind" about a stop it overstated by 7.5 s
    (14 Sep 2026).

    `None` if either half is unknown: a stop cost built from one of them is not
    a stop cost.
    """
    if (litres is None or not refuel_rate_lps or refuel_rate_lps <= 0
            or pit_loss_s is None):
        return None
    if litres < 0:
        return None
    lane = pit_loss_s
    if pit_loss_source == PIT_LOSS_MEASURED:
        # A lane-only figure: the standing time before the hose is not in it.
        lane += PIT_DEAD_TIME_S
    # `PIT_LOSS_MEASURED_EX_FUEL` and a declared loss already carry it.
    return litres / refuel_rate_lps + lane


def rejoin_against(gap_behind_s: float | None,
                   ours_lost_s: float | None) -> Rejoin | None:
    """Whether we come out ahead of the car currently behind us.

    `gap_behind_s` is how far back he is. He gains our whole stop, so we stay
    ahead only if he was further back than the stop costs.
    """
    if gap_behind_s is None or ours_lost_s is None:
        return None
    if gap_behind_s < 0:
        return None
    margin = gap_behind_s - ours_lost_s
    ahead = None if abs(margin) < REJOIN_MARGIN_S else margin > 0
    return Rejoin(ours_lost_s=ours_lost_s, their_gap_s=gap_behind_s,
                  ahead=ahead, margin_s=margin)


@dataclass
class GapTrend:
    """One car's gap over time, and how fast it is CLOSING.

    Keyed by lap, so a gap sampled twice on the same lap replaces rather than
    doubles - the readers run at one or two hertz and a lap is a minute.

    ### It has to know which car it is watching

    **Without that it regresses through an overtake and reports the answer as
    pace.** Measured on this class as it first stood: when we passed the car
    ahead and the next one was 12 s up the road it reported "losing 1.72 s a
    lap"; when the car ahead pitted, "losing 9.79". Both are well-formed
    confident numbers about a car that is no longer there, which is the shape
    CLAUDE.md rule 9 names. `subject` is whatever identifies the car - a driver
    id from the roster - and a change of subject throws the history away,
    because it IS a different history.

    ### The number means "the gap is shrinking", on both sides

    A single `GapTrend` class is built twice, once for the car ahead and once
    for the car behind, and "positive means we are catching him" is only true
    of one of them - on the car behind a shrinking gap means HE is catching US,
    which demands the opposite driving. That is rule 13 exactly. So the rate
    here means one thing on both sides - the gap is closing at this many
    seconds a lap - and `side` says who that is good news for. The sentence
    differs; the number does not.
    """
    side: str = "ahead"
    seen: dict[int, float] = field(default_factory=dict)
    subject: object = None
    # **Every reading, by lap and by whose it was** - `lap -> subject ->
    # [count, last gap, order]`. `seen` and `subject` are DERIVED from this
    # on every note, so a misread never destroys anything: it is outvoted.
    _reads: dict = field(default_factory=dict, repr=False)
    _order: int = field(default=0, repr=False)

    def note(self, lap: int | None, gap_s: float | None,
             subject: object = None) -> None:
        """Record one reading. The car a LAP was about is decided by vote.

        ### 14 Sep 2026 - one misread used to erase five laps

        **A change of subject threw the whole history away, and one frame
        was enough to change it.** Bathurst, session 176: the car ahead was
        the same cluster on every lap 1-14, 16 to 31 readings a lap - and on
        laps 2, 4, 5, 6, 7 and 10 a single reading carried another name (a
        board row misread, `Car #4` or `Car #31` once each). Each of those
        wiped the history, so `MIN_LAPS_FOR_TREND` consecutive laps never
        accumulated and `closing_call` could not be reached all race.

        So the car a lap is about is the MAJORITY of that lap's readings,
        and the history is never deleted - it is re-derived. `seen` holds
        the laps of the current subject's run: for each lap, the last
        reading of that car, where the lap has one. A genuine overtake still
        starts a new history, because from the lap it happens on the new car
        carries the readings; a flicker is a minority and changes nothing.

        **The newest lap decides who the subject is, and the incumbent wins
        a tie.** At a crossing the newest lap may hold a single reading, and
        one reading of a new car IS what an overtake looks like at first -
        so a lone reading of a new name still moves the subject, exactly as
        before, until the lap's next readings outvote it. The difference is
        that when they do, the old car's laps come back instead of being gone.

        A reading with no subject (`None`) is a wildcard: it votes for nobody
        and stands in for whichever car the lap is about.
        """
        if lap is None or gap_s is None:
            return
        lap = int(lap)
        self._order += 1
        slot = self._reads.setdefault(lap, {}).setdefault(subject, [0, 0.0, 0])
        slot[0] += 1
        slot[1] = float(gap_s)
        slot[2] = self._order
        self._rederive()

    def _majority(self, lap: int, incumbent: object) -> object:
        """The car most read on `lap`; the incumbent on a tie; None if unvoted."""
        votes = {who: slot[0] for who, slot in self._reads.get(lap, {}).items()
                 if who is not None}
        if not votes:
            return incumbent
        best = max(votes.values())
        if incumbent in votes and votes[incumbent] == best:
            return incumbent
        # Deterministic among equals: the one read most recently.
        tied = [who for who, n in votes.items() if n == best]
        return max(tied, key=lambda who: self._reads[lap][who][2])

    def _rederive(self) -> None:
        """Rebuild `subject` and `seen` from the readings. Rebinds, never
        mutates, so a snapshot taken on another thread is never half-built."""
        if not self._reads:
            self.seen, self.subject = {}, None
            return
        newest = max(self._reads)
        subject = self._majority(newest, self.subject)
        seen: dict[int, float] = {}
        for lap, by_who in self._reads.items():
            if subject is not None and self._majority(lap, subject) != subject:
                # A lap that was about another car is not this car's lap,
                # even where a stray reading of this one landed in it.
                continue
            mine = [slot for who, slot in by_who.items()
                    if who == subject or who is None]
            if mine:
                seen[lap] = max(mine, key=lambda slot: slot[2])[1]
        self.subject = subject
        self.seen = seen

    @property
    def readings(self) -> int:
        """How many readings have ever been noted - moves on every one, so a
        reader can tell whether the board has been read since a moment."""
        return self._order

    def latest(self) -> float | None:
        """The most recent gap, or `None` where nothing has been read.

        The newest LAP rather than the newest insertion: `seen` is keyed by lap
        and a frame arriving out of order would otherwise make an older reading
        the current one.
        """
        if not self.seen:
            return None
        return self.seen[max(self.seen)]

    def new_session(self) -> None:
        """CLAUDE.md rule 11. A gap history is about one race."""
        self.seen = {}
        self.subject = None
        self._reads = {}
        self._order = 0

    def _window(self, over_laps: int) -> list[int]:
        """The last `over_laps` CONSECUTIVE laps, newest last.

        **Consecutive, not merely the last N keys.** The board is unreadable
        for long stretches by design, and taking the last five samples fitted a
        line straight through the holes: five readings spanning laps 3, 4, 15,
        16, 17 came back as a trend "over the last 5 laps", and a series broken
        by our own pit stop reported the stop itself as ten seconds a lap of
        lost pace.
        """
        laps = sorted(self.seen)
        if not laps:
            return []
        run = [laps[-1]]
        for lap in reversed(laps[:-1]):
            if run[0] - lap != 1:
                break
            run.insert(0, lap)
            if len(run) >= over_laps:
                break
        return run

    def closing_s_per_lap(self, over_laps: int = MIN_LAPS_FOR_TREND
                          ) -> tuple[float | None, int]:
        """Seconds a lap the gap is CLOSING, and the consecutive laps behind it.

        Positive means the gap is shrinking, whichever side this is. See the
        class docstring on why that is not "we are catching him".

        **The median of ADJACENT differences, with the largest one trimmed,
        and a step is why.** Session 135, 6 Sep 2026: the driver crashed on
        lap 2 and lost about ten seconds in that one lap, and at lap 5 the fit
        still reached back across it and reported "you are losing 1.6 seconds a
        lap to the car ahead" - at medium confidence, under a helmet - when the
        recent laps were going the other way and he passed that car two laps
        later.

        The two ANALOGOUS failures were already defended above and neither
        helps: a change of `subject` throws the history away, and `_window`
        demands consecutive laps because a series broken by our own stop
        "reported the stop itself as ten seconds a lap of lost pace". A crash
        breaks neither - it is consecutive and it is the same car. Those guards
        catch a hole in the DATA; this catches a step in the VALUE.

        **An OUTLIER and a STEP are different contaminations and they do not
        take the same estimator.** `analysis.wear.trend_slope` is Theil-Sen and
        is right for its own question - one lap five seconds off the pace that
        then returns to trend. A crash is not that: the ten seconds STAY lost,
        so every pairwise slope that spans the crash is contaminated, which at
        five laps is up to six of the ten pairs. Theil-Sen was tried here and a
        critic measured it failing: with the step in the MIDDLE of the window
        it returns "losing 1.92 a lap" while the driver is closing at 1.0. It
        only appeared to work because session 135's crash happened to sit at
        the very start, which is the best place for it rather than the worst.

        **A step contaminates exactly ONE adjacent difference.** Five laps give
        four differences; dropping the single largest leaves three clean ones,
        which is immunity to exactly one incident - the failure that was
        actually measured. On clean data every difference is alike and the trim
        changes nothing. On a genuinely accelerating close it under-reports
        slightly, which is the same direction `TREND_WORTH_SAYING_S` already
        chose deliberately: it will miss real trends rather than invent them.

        The count travels with the rate because a slope through three points is
        not a trend - CLAUDE.md rule 4 - and it still means the consecutive
        laps fitted, unchanged by this.
        """
        laps = self._window(over_laps)
        if len(laps) < 3:
            return None, len(laps)
        steps = [self.seen[b] - self.seen[a] for a, b in zip(laps, laps[1:])]
        if len(steps) >= 3:
            worst = max(range(len(steps)), key=lambda i: abs(steps[i]))
            steps = steps[:worst] + steps[worst + 1:]
        return -median(steps), len(laps)

    def laps_to_catch(self, over_laps: int = MIN_LAPS_FOR_TREND,
                      laps_left: int | None = None) -> float | None:
        """Laps until the gap reaches zero at the present rate, or `None`.

        `None` where we are not closing, rather than a negative number or an
        infinity: "never, at this rate" is the answer, and it is not a quantity
        of laps.

        **And `None` where the answer runs past the flag.** The denominator has
        a standard deviation near 0.5 s a lap, so a "seven laps" call has a
        one-sigma range of four to thirty-three; just above the threshold an
        eight-second gap returns fifty laps in a twenty-lap race. A number that
        large carries no information and it is spoken under a helmet, so it is
        not spoken at all.
        """
        rate, count = self.closing_s_per_lap(over_laps)
        if rate is None or count < MIN_LAPS_FOR_TREND:
            return None
        if rate <= TREND_WORTH_SAYING_S:
            return None
        latest = self.seen[max(self.seen)]
        if latest <= 0:
            return None
        laps = latest / rate
        if laps_left is not None and laps > laps_left:
            return None
        return laps
