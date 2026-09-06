"""Conditioning the 2 Hz gap signal so something can be differentiated from it.

`gaps.py` holds the primitives - what a stop costs, where it puts us. This is
the layer underneath: turning a stream of OCR readings into a rate that is not
mostly noise, and refusing to produce one when it would be.

### Raw 2 Hz OCR is not differentiable

A gap read off the screen twice a second carries a quantisation error of about
a quarter of a second, and any consumer computing `dg/dt` from two adjacent
samples is dividing that by half a second. The answer is noise with a plausible
sign. Everything here exists to stop that happening.

**The plausibility gate.** Between consecutive samples a gap cannot move faster
than about 3 s per second of wall clock - that is two cars a lap apart in pace,
which does not happen. A jump past it is an OCR misread or the car in the slot
changing, and the sample is REJECTED rather than clamped: clamping turns "I
misread" into a confident value, which is CLAUDE.md rule 9.

**Theil-Sen, not least squares.** The median of every pairwise slope. This
codebase already learned it once, in `analysis/wear.trend_slope`: on the 11 Aug
Monza session one un-struck lap five seconds off the pace moved a least-squares
slope by 90 ms a lap and took the sign with it. A single surviving misread does
the same thing here, and the median shrugs it off. The estimator is imported
rather than rewritten, so there is one answer to "what is the slope of these
points" in the app.

**Staleness, enforced where the value is USED.** A gap-derived number is worth
nothing three seconds later; a fuel-derived one lasts about fifteen; a pit
event never expires, because an event is a point and not a level. A stale value
reports as unknown, never as last-known - which is the whole difference between
degrading honestly and degrading quietly.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from pitcrew.analysis.wear import trend_slope

# **A gap cannot move faster than this.** Two cars a lap apart in pace differ
# by about 1.5 s a lap on a 90 s circuit, which is 0.017 s per second; 3.0
# leaves two orders of magnitude of headroom and still catches an OCR misread,
# which moves a gap by whole seconds between one frame and the next.
MAX_GAP_RATE_S_PER_S = 3.0

# The trailing window a rate is fitted over, and the samples that need to be in
# it. Ten seconds at 2 Hz is twenty readings.
RATE_WINDOW_S = 10.0
MIN_SAMPLES_FOR_RATE = 6

# How long a derived value stays true. A pit event is a point in time and does
# not expire; a gap is a level and expires quickly.
GAP_STALE_S = 3.0
FUEL_STALE_S = 15.0


@dataclass(frozen=True)
class GapSample:
    """One screen reading, with everything needed to use it later.

    **A gap with no track position attached is nearly useless.** Section 4 of
    the spec - where on the lap we gain and lose - cannot bin anything without
    `track_s`, and a gap sampled at an unknown point of the lap cannot be
    compared with the same gap a lap later. It is recorded at ingest because it
    cannot be recovered afterwards.

    `ok` is per FIELD, not per frame: OCR fails one box at a time, and a
    confident gap beside a garbled fuel figure is the ordinary case.
    """
    at_s: float                      # wall clock, the join key
    gap_s: float | None
    track_s: float | None = None     # ego lap distance, interpolated to at_s
    lap: int | None = None
    position: int | None = None
    subject: object = None           # who the gap is TO
    ok: bool = True
    # "ahead" or "behind". Without it the two trends' samples were one list
    # that nothing could split again, and the sector map bins the car AHEAD.
    side: str = "ahead"


@dataclass
class GapSignal:
    """A conditioned stream of gap readings for one slot.

    One instance per slot - the car ahead, the car behind - and the slot is not
    the car. `subject` is the car currently in it, and a change of subject
    clears everything, because a series across two cars is a series about
    neither.
    """
    side: str = "ahead"
    samples: list[GapSample] = field(default_factory=list)
    subject: object = None
    rejected: int = 0

    # --- ingest -----------------------------------------------------------

    def note(self, sample: GapSample) -> bool:
        """Take one reading. Returns whether it was kept.

        Rejects rather than clamps, and says so by returning False - a caller
        that wants to know how blind it is can count them.
        """
        if sample.subject is not None and sample.subject != self.subject:
            if self.subject is not None:
                self.samples = []
                self.rejected = 0
            self.subject = sample.subject
        if not sample.ok or sample.gap_s is None:
            return False
        if sample.gap_s < 0:
            return False
        if not self._plausible(sample):
            self.rejected += 1
            return False
        self.samples.append(sample)
        self._forget_before(sample.at_s - RATE_WINDOW_S * 3)
        return True

    def _plausible(self, sample: GapSample) -> bool:
        if not self.samples:
            return True
        last = self.samples[-1]
        elapsed = sample.at_s - last.at_s
        if elapsed <= 0:
            return False
        moved = abs(sample.gap_s - (last.gap_s or 0.0))
        return moved <= MAX_GAP_RATE_S_PER_S * elapsed

    def _forget_before(self, at_s: float) -> None:
        self.samples = [s for s in self.samples if s.at_s >= at_s]

    def new_session(self) -> None:
        """CLAUDE.md rule 11. All of this describes one race."""
        self.samples = []
        self.subject = None
        self.rejected = 0

    # --- read -------------------------------------------------------------

    def latest(self, now_s: float) -> float | None:
        """The gap as of now, or `None` if the reading has gone stale.

        **Enforced here, at the point of use.** A staleness check done only at
        ingest lets a value that was fresh when it arrived be read an hour
        later as though it still meant something.
        """
        if not self.samples:
            return None
        last = self.samples[-1]
        if now_s - last.at_s > GAP_STALE_S:
            return None
        return last.gap_s

    def rate_s_per_s(self, now_s: float,
                     window_s: float = RATE_WINDOW_S
                     ) -> tuple[float | None, float | None, int]:
        """`(closing rate, spread, samples)` over the trailing window.

        Positive means the gap is shrinking - the same convention on both
        sides, so that one word does not mean two things. See
        `gaps.GapTrend` for the same rule at lap resolution.

        The spread is the interquartile range of the pairwise slopes, which is
        the honest confidence band for a Theil-Sen fit: `None` where there are
        too few pairs for a quartile to mean anything.
        """
        window = [s for s in self.samples
                  if now_s - s.at_s <= window_s and s.gap_s is not None]
        if len(window) < MIN_SAMPLES_FOR_RATE:
            return None, None, len(window)
        if now_s - window[-1].at_s > GAP_STALE_S:
            return None, None, len(window)
        # `trend_slope` is Theil-Sen over (x, y) integers. Times are scaled to
        # milliseconds so the shared estimator can be used unchanged rather
        # than a second one written for the same question.
        points = [(int(s.at_s * 1000), int(s.gap_s * 1000)) for s in window]
        slope = trend_slope(points)
        if slope is None:
            return None, None, len(window)
        pairs = [
            (b[1] - a[1]) / (b[0] - a[0])
            for i, a in enumerate(points) for b in points[i + 1:]
            if b[0] != a[0]]
        spread = None
        if len(pairs) >= 4:
            ordered = sorted(pairs)
            quarter = len(ordered) // 4
            spread = ordered[-quarter - 1] - ordered[quarter]
        return -slope, spread, len(window)


def fresh(at_s: float | None, now_s: float, ttl_s: float) -> bool:
    """Whether a value taken at `at_s` is still worth reading."""
    return at_s is not None and 0 <= now_s - at_s <= ttl_s
