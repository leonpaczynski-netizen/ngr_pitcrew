"""Which way a tyre's split against its opposite number is going, per lap.

**The split is the reading on this car with evidence behind it.** An absolute
tyre temperature is endogenous - a consequence of how hard the tyre is being
worked rather than an input to grip - and no optimal window has ever been
published for GT7; measured here, minimum corner speed against temperature has
slopes of OPPOSITE SIGN at Monza and Spa with R² under 0.2. The splits do not
have that problem. Measured across the archive, the rear-front and RR-RL gaps
are monotone and match the measured wear map at **r=+0.82**.

So the dashboard already showed the split as a figure. What it could not say
was whether that figure was growing or shrinking, which is the difference
between a car that is going away and one that has settled.

### Per lap, never per frame

Raw frames are useless for this. Per-lap peaks reach 117.8 °C at Monza and
158.8 at Spa, and a single frame's split is dominated by where in the lap it
was taken. Every sample here is a **whole-lap mean per corner**, taken at the
crossing, which is the same unit the archive's r=+0.82 was measured in.

### Why the threshold is what it is, and what kind of number it is

`RATE_WORTH_SAYING_C` is **derived, not measured.** The instrument-noise work
put a per-corner per-lap temperature floor at 0.9-1.4 °C. A split is a
difference of two corners, so its own floor is about √2 × 1.4 ≈ 2.0 °C. Fit a
least-squares slope through five laps and the standard error of that slope is
σ / (sd(x)·√n) = 2.0 / (1.41 × 2.24) ≈ 0.63 °C/lap. Two standard errors is
1.26, and that is where the threshold sits.

**This is not the same statistical situation as `race/gaps.py`**, and the
difference is worth stating because the two look alike. A gap between cars is
a random walk - the cumulative sum of per-lap pace differences - so fitting a
line to it and judging the slope against an iid-sized threshold is spurious
regression, which is why that module's threshold is five times larger than it
first appears it should be. A tyre split is not a sum of anything: it is a
noisy measurement of a state that happens to drift. An ordinary slope is the
right tool here, and the ordinary standard error is the right yardstick.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

CORNERS = ("fl", "fr", "rl", "rr")
PAIRS = {"fl": "fr", "fr": "fl", "rl": "rr", "rr": "rl"}

# Laps of history before a rate is worth quoting. Five, matching the gap
# module - three points is a slope through noise, five is a trend.
MIN_LAPS_FOR_TREND = 5

# °C a lap below which the movement is not distinguishable from the
# instrument. Derived from the measured per-corner floor - see the module
# docstring for the arithmetic. Labelled derived wherever it is shown.
RATE_WORTH_SAYING_C = 1.25

# Nothing older than this can describe the tyres that are on the car now.
WINDOW_LAPS = 8

# **What the driver reads on the board: a 3-second mean, not a frame.**
#
# The dashboard's own docstring said it was "fed a smoothed temperature, never
# a raw frame" and it was not - `_board_temps` returned a single packet, so
# the four numbers jittered at 60 Hz against a per-lap signal of about 10 °C.
# The driver asked for instant or a three-second average; three seconds is the
# better of the two and it is not close. Sixty Hz means ~180 frames in the
# window, which flattens frame jitter without lagging anything he could act
# on - he glances at this on a straight, and a straight is longer than three
# seconds.
#
# **This is a display filter and nothing else.** The split trend above is
# computed from WHOLE-LAP means, which is the unit the r=+0.82 against the
# wear map was measured in; a three-second mean is not evidence of anything
# and is never used as any.
BOARD_SMOOTHING_S = 3.0


@dataclass
class SplitHistory:
    """Whole-lap corner means, and the slope of any pair's split.

    **Reset at every session boundary, and the reset has a caller.** State
    that outlives a session gets read as though it belongs to this one: a race
    once opened judging its fresh tyres against practice's worn ones, and a
    practice gauge reading was spoken aloud as a measured race number two laps
    in. `new_session` exists for that, and `controller` calls it - a reset with
    no caller is the shape of that defect, not the fix for it.
    """

    laps: deque = field(default_factory=lambda: deque(maxlen=WINDOW_LAPS))

    def new_session(self) -> None:
        """Forget everything. Called when a session opens, not at app exit."""
        self.laps.clear()

    def note_lap(self, temps: dict[str, float | None] | None) -> None:
        """Take one whole-lap sample: the four corner means at a crossing.

        A lap missing any corner is dropped rather than part-filled. Three
        corners cannot make a split, and a gap in the middle of a series
        would be fitted straight through as though the lap had been measured.
        """
        if not temps:
            return
        got = {c: temps.get(c) for c in CORNERS}
        if any(v is None for v in got.values()):
            return
        self.laps.append({c: float(v) for c, v in got.items()})

    def split_now(self, corner: str) -> float | None:
        """The most recent lap's split for this corner, or None.

        Positive only: the cooler side of a pair returns None, because "13
        degrees cooler" is the same finding said about the wrong corner.
        """
        if not self.laps:
            return None
        last = self.laps[-1]
        gap = last[corner] - last[PAIRS[corner]]
        return gap if gap > 0 else None

    def rate(self, corner: str) -> tuple[float | None, int]:
        """`(°C per lap, laps behind it)` for this corner's split.

        The rate is `None` where there is not enough history or the movement
        is inside the instrument - which is not the same as a rate of zero,
        and the caller must not render it as one. The lap count comes back
        either way so a caller can say how much is behind the answer.
        """
        count = len(self.laps)
        if count < MIN_LAPS_FOR_TREND:
            return None, count
        series = [lap[corner] - lap[PAIRS[corner]] for lap in self.laps]
        n = len(series)
        mean_x = (n - 1) / 2.0
        mean_y = sum(series) / n
        spread = sum((i - mean_x) ** 2 for i in range(n))
        if spread == 0:
            return None, count
        slope = sum((i - mean_x) * (y - mean_y)
                    for i, y in enumerate(series)) / spread
        if abs(slope) < RATE_WORTH_SAYING_C:
            return None, count
        return slope, count
