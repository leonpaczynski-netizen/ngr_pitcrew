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

from pitcrew.strategy.model import PIT_DEAD_TIME_S, PIT_LOSS_MEASURED
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
TREND_WORTH_SAYING_S = 0.8


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
        lane += PIT_DEAD_TIME_S
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

    def note(self, lap: int | None, gap_s: float | None,
             subject: object = None) -> None:
        """Record one reading. A change of subject starts a new history."""
        if lap is None or gap_s is None:
            return
        if subject is not None and subject != self.subject:
            if self.subject is not None:
                self.seen = {}
            self.subject = subject
        self.seen[int(lap)] = float(gap_s)

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
