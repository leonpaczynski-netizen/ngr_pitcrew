"""Which way a tyre's split against its opposite number is going, per lap.

**The split is the reading on this car with evidence behind it.** An absolute
tyre temperature is endogenous - a consequence of how hard the tyre is being
worked rather than an input to grip - and no optimal window has ever been
published for GT7.

**The endogeneity is measured, and the evidence for it is not what this file
used to cite.** The old sentence here said minimum corner speed against
temperature had "slopes of OPPOSITE SIGN at Monza and Spa with R² under 0.2".
That was per-corner OLS on 8-11 laps and it did not survive a proper
specification: with corner x stint fixed effects, `lap_in_stint` held and
standard errors clustered by lap, **both slopes are negative and neither is
significant** - Monza -0.809 (t -1.57), Spa -0.227 (t -0.29). The comparison
was confounded five ways over as well (two circuits, two cars, two compounds,
a 4x wear multiplier, two formats). What replaced it is a direct measurement,
4 Sep 2026, 48 Daytona laps: rear slip against rear temperature within a cell
of the same 100 m, gear, speed band and throttle band gives +0.002772 per °C,
18 of 22 cells positive against a permutation null of 47.0% - and **lagging
the temperature by one second collapses the slope by a factor of 146 and the
positive share to exactly 50.0%.** Slip heats the tyre; the tyre does not lose
grip because it is hot. The conclusion is unchanged and is now demonstrated
rather than argued.

**The splits do not have that problem, and this is exactly what they have.**
Measured 3 Sep 2026, v1.71, Huracán GT3, Daytona session 118, 71,449 frames:
the rear-front gap runs +2.90 °C on lap 1 to +12.65 on lap 10 and the RR-RL
gap +0.10 to +4.00, both monotone. Across the four corners of the car, per-lap
mean temperature against measured per-lap wear rate comes out at **r=+0.82**
(FL 62.5 °C / 0.0275 per lap … RR 75.7 °C / 0.0570). ⚠️ **n=4, and it is an
association**: both quantities are driven by load. It is not a claim that
temperature predicts wear, and it is not a grip claim of any kind. What it
buys is that the gap is a **finer instrument than the wear gauge for the same
thing** - the gauge quantises at 2.8-3.3% of tyre life per pixel and the gap
moves continuously.

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

    def new_stint(self) -> None:
        """Forget everything, at a pit stop.

        **The session reset is not enough, and the axle block is what made
        that matter.** The window is eight laps and a stop lands in the
        middle of it, so a fit across the stop describes two sets of rubber
        as though they were one. Driven through a realistic stint - the old
        set ramping +6 to +20 degC and a fresh one restarting at +3 and
        opening at +1 a lap - the board drew *"REAR OVER FRONT · 8 laps ·
        settling 2.0/lap"* for six consecutive laps while the gap was in
        fact opening. The sample count is a lie in the same breath: half
        those laps were a different tyre.

        **At every stop, whether or not a set went on.** The tri-state tyre
        detector can say "cannot tell", and an unknown is not a no
        (CLAUDE.md 4.3); and even a fuel-only stop parks a stationary car
        for half a minute, so the laps either side of it are not one series
        whatever came off. Losing history costs the trend five laps of
        silence, which is honest. Keeping it costs a brake-balance decision.
        """
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

    def axle_split_now(self) -> float | None:
        """The last lap's **rear axle mean minus front axle mean**, signed.

        **Signed, where `split_now` is not, and that is not an inconsistency.**
        A left tyre and a right tyre are interchangeable, so "13 °C cooler" is
        the same finding said about the wrong corner and only the hotter side
        is worth reporting. A front axle and a rear axle are not
        interchangeable: rears hotter is a rear-limited car and fronts hotter
        is a front-limited one, and those ask for opposite changes - CLAUDE.md
        §5.5's own worked example is *"Brake balance one click rearward.
        Fronts are going first."* Both directions are findings, so the sign
        travels here and the caller says which axle it is in words. A number
        whose sign the driver has to decode is exactly what rule 13 is about.

        `None` before any whole lap has been sampled. Never a zero.
        """
        if not self.laps:
            return None
        last = self.laps[-1]
        return ((last["rl"] + last["rr"]) / 2.0
                - (last["fl"] + last["fr"]) / 2.0)

    def rate(self, corner: str) -> tuple[float | None, int]:
        """`(°C per lap, laps behind it)` for this corner's split.

        The rate is `None` where there is not enough history or the movement
        is inside the instrument - which is not the same as a rate of zero,
        and the caller must not render it as one. The lap count comes back
        either way so a caller can say how much is behind the answer.
        """
        return self._trend([lap[corner] - lap[PAIRS[corner]]
                            for lap in self.laps])

    def axle_rate(self) -> tuple[float | None, int]:
        """`(°C per lap, laps behind it)` for the rear-front split.

        **Judged against the same floor as a corner pair, deliberately.** An
        axle mean averages two corners, so if the two corners' noise were
        independent the axle gap's floor would fall by √2 and this threshold
        would be too strict by that much. It is not known to be independent -
        both corners of an axle see the same load transfer, the same kerb and
        the same air - so the reduction cannot be claimed, and the
        same-corner floor is the conservative bound. One threshold, stated,
        rather than two that drift: `RATE_WORTH_SAYING_C` is derived and not
        measured, and it is labelled that way wherever it is shown.
        """
        return self._trend([((lap["rl"] + lap["rr"]) / 2.0
                             - (lap["fl"] + lap["fr"]) / 2.0)
                            for lap in self.laps])

    def _trend(self, series: list[float]) -> tuple[float | None, int]:
        """The least-squares slope of one series, or None inside the floor."""
        count = len(self.laps)
        if count < MIN_LAPS_FOR_TREND:
            return None, count
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
