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

### Closing rate is the cheapest pace signal on the screen

Comparing lap times to judge whether you are catching somebody costs 0.918 s of
lap-to-lap noise. A difference of GAPS does not: both cars ran the same lap in
the same traffic on the same track state, so most of that noise is common and
cancels. Four laps of the gap ahead falling 0.4 s a lap is a finding; four laps
of lap times looking 0.4 s quicker is not.

### What is NOT validated here, and it matters

**The gap boxes were empty in every frame of footage available.** Measured over
a whole 48-minute Spa replay, every gap readout on every frame showed
`--:--.---`, because a replay does not draw them. So `hud_time.read_seconds` is
validated against the fastest-lap banner - white on purple, known value,
133.484 read exactly - and the gap FIELD is validated only in that it correctly
refuses a box of dashes.

Reading a live gap has never been exercised. The failure direction is safe:
`read_seconds` refuses anything it cannot read rather than guessing, so an
unread gap is `None` and every function here returns `None` in turn. But
nothing below should be believed on a race weekend until one frame of real
bumper-cam footage with the gaps drawn has been through it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.telemetry.hud_time import read_seconds

# Below this many seconds of difference, "you come out ahead of him" is a claim
# the arithmetic cannot support: the pit loss itself is only known to about a
# second, and a rival's own next lap moves the gap by more than that.
REJOIN_MARGIN_S = 3.0

# Laps of gap history before a closing rate is worth quoting. Three points is a
# slope through noise; five is a trend.
MIN_LAPS_FOR_TREND = 5

# Seconds a lap below which a closing rate is not worth saying - it is inside
# what one lap of traffic does.
TREND_WORTH_SAYING_S = 0.15


# The gap text sits in the right of the row and runs PAST the board's own right
# edge - `board.own_row` stops at the country flag, and the interval is drawn
# beyond it. Expressed in row heights so it survives a resolution change.
GAP_BAND_LEFT, GAP_BAND_RIGHT = 1.6, 1.4


def read_gaps(frame, board) -> tuple[float | None, float | None]:
    """`(ahead, behind)` in seconds, from the two rows either side of ours.

    GT7 inserts a gap readout immediately above and below the driver's own row.
    `None` for either where the box carries no value - which on all footage
    available is BOTH, always: a replay draws `--:--.---` and nothing else. See
    the module docstring on what that leaves unvalidated.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3 or board is None:
        return None, None
    x0, y0, x1, y1 = board
    height = y1 - y0 + 1
    left = max(0, x1 - int(GAP_BAND_LEFT * height))
    right = min(frame.shape[1], x1 + int(GAP_BAND_RIGHT * height))
    out = []
    for top in (y0 - height, y1 + 2):
        band = frame[max(0, top):max(0, top) + height, left:right]
        out.append(read_seconds(band) if band.size else None)
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
                 pit_loss_s: float | None) -> float | None:
    """Total time a stop costs: the fill, plus the lane.

    `pit_loss_s` is the track constant - transit and the dead time - measured
    once per circuit. `None` if either half is unknown: a stop cost built from
    one of them is not a stop cost.
    """
    if (litres is None or not refuel_rate_lps or refuel_rate_lps <= 0
            or pit_loss_s is None):
        return None
    if litres < 0:
        return None
    return litres / refuel_rate_lps + pit_loss_s


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
    """One car's gap over time, and how fast it is changing.

    Keyed by lap, so a gap sampled twice on the same lap replaces rather than
    doubles - the readers run at one or two hertz and a lap is a minute.
    """
    seen: dict[int, float] = field(default_factory=dict)

    def note(self, lap: int | None, gap_s: float | None) -> None:
        if lap is None or gap_s is None:
            return
        self.seen[int(lap)] = float(gap_s)

    def new_session(self) -> None:
        """CLAUDE.md rule 11. A gap history is about one race."""
        self.seen = {}

    def closing_s_per_lap(self, over_laps: int = MIN_LAPS_FOR_TREND
                          ) -> tuple[float | None, int]:
        """Seconds a lap the gap is closing, and the laps behind it.

        Positive means we are catching him. A least-squares slope over the last
        `over_laps` samples, and the count travels with it because a slope
        through three points is not a trend - CLAUDE.md rule 4.

        **A difference of gaps, not of lap times.** Both cars ran the same lap
        in the same traffic, so the lap-to-lap noise that makes a lap-time
        comparison useless at this driver's 0.918 s sigma is largely common and
        cancels here.
        """
        laps = sorted(self.seen)[-over_laps:]
        if len(laps) < 3:
            return None, len(laps)
        mean_lap = sum(laps) / len(laps)
        mean_gap = sum(self.seen[k] for k in laps) / len(laps)
        spread = sum((k - mean_lap) ** 2 for k in laps)
        if spread <= 0:
            return None, len(laps)
        slope = sum((k - mean_lap) * (self.seen[k] - mean_gap)
                    for k in laps) / spread
        # A shrinking gap means we are closing, so the sign is flipped for the
        # caller: "closing at 0.4" reads better than "the gap is at minus 0.4".
        return -slope, len(laps)

    def laps_to_catch(self, over_laps: int = MIN_LAPS_FOR_TREND
                      ) -> float | None:
        """Laps until the gap reaches zero at the present rate, or `None`.

        `None` where we are not closing, rather than a negative number or an
        infinity: "never, at this rate" is the answer, and it is not a quantity
        of laps.
        """
        rate, count = self.closing_s_per_lap(over_laps)
        if rate is None or count < MIN_LAPS_FOR_TREND:
            return None
        if rate <= TREND_WORTH_SAYING_S:
            return None
        latest = self.seen[max(self.seen)]
        if latest <= 0:
            return None
        return latest / rate
