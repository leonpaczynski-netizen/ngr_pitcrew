"""When a set of laps is really two sets, say so instead of averaging it.

`CLAUDE.md` §4.1 is about the driver and the telemetry: *where the two disagree,
that disagreement is the finding — surface it, do not average it.* The same rule
applies when the laps disagree with each other.

**The case this was built for.** Session 60, 21 Aug 2026: ten laps deliberately
short-shifted, then two at full RPM. The burns are 5.15–5.36 L and 6.66–6.81 L,
a 27% step with a clean 1.3 L gap and nothing in between. The app cannot tell
the two apart — `short_shift_rpm` reads 0.0 on all twelve — so it took a
weighted median of the lot and reported **5.28 L/lap**, which is the
short-shifted figure. A plan costed on it would go into a full-RPM race a
quarter light on fuel.

**Nothing here identifies the cause.** It does not know that one group was
short-shifted; it knows the laps do not describe one behaviour. Naming the
cause would be inventing it. What it produces is a refusal to collapse two
answers into one, with both answers and their lap counts attached, so the
driver picks the one he is about to race.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# Below this the split is ordinary lap-to-lap scatter. The measured short-shift
# saving is 21-25%, so the signal this exists to catch clears it comfortably;
# fuel scatter within one discipline is a few percent.
MIN_GAP_FRACTION = 0.12
# One outlying lap is an outlying lap. Two is the beginning of a second group -
# which is exactly the size of the full-RPM half of session 60, so a floor of
# three would have missed the case this was written for.
MIN_GROUP = 2


@dataclass(frozen=True)
class Split:
    """Two populations where one was expected."""

    low: float
    low_laps: int
    high: float
    high_laps: int

    @property
    def gap_fraction(self) -> float:
        return (self.high - self.low) / self.high

    def describe(self, units: str = "L/lap") -> str:
        return (f"these laps are two populations, not one: "
                f"{self.low_laps} at about {self.low:.3g} {units} and "
                f"{self.high_laps} at about {self.high:.3g} {units}, "
                f"{self.gap_fraction * 100:.0f}% apart with nothing between "
                f"them. A single figure across both describes neither. Decide "
                f"which one the race will be run at")


def find_split(values, *, min_gap: float = MIN_GAP_FRACTION,
               min_group: int = MIN_GROUP) -> Split | None:
    """Two clusters separated by a gap, or None if the values are one group.

    Split at the **largest** gap between consecutive sorted values, which is
    the only place a two-group structure can divide. Deliberately not a
    clustering algorithm: with a dozen laps the largest gap is the whole
    signal, and anything cleverer would find structure in noise.
    """
    ordered = sorted(v for v in values if v is not None and v > 0)
    if len(ordered) < min_group * 2:
        return None

    gaps = [(ordered[i + 1] - ordered[i], i) for i in range(len(ordered) - 1)]
    widest, at = max(gaps)
    low, high = ordered[:at + 1], ordered[at + 1:]
    if len(low) < min_group or len(high) < min_group:
        return None

    low_mid, high_mid = median(low), median(high)
    if high_mid <= 0 or (high_mid - low_mid) / high_mid < min_gap:
        return None

    # The gap has to be the dominant feature, not the largest of many similar
    # ones - otherwise a smoothly spread set splits at an arbitrary point.
    others = sorted(g for g, _ in gaps)
    if len(others) > 1 and widest < 2.0 * median(others[:-1]):
        return None

    return Split(low_mid, len(low), high_mid, len(high))
