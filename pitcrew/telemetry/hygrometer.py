"""GT7's hygrometer, read off the HUD - plan row 5.13.

**The feed has no rain channel, and the HUD has one.** The hygrometer sits left of
the tyre-wear bars on the same panel `hud.locate_gauge` already finds. Calibrated
14 Sep 2026 on two flat-screen 1080p captures (`reference_gt7_hygrometer_behaviour`):
the driver's video with water on the track, and the dry Suzuka race of 13 Sep.

### What it measures, which is not what the name suggests

**Water under the car, now - not how wet the circuit is.** A fill bar that
follows the surface within tenths of a second: empty on a dry track, 57-81 of 86
px on a wet one, and back to empty in about 0.8 s through a tunnel on that same
wet track. So one frame is a reading of the last few metres, and the question a
race needs - is it wet - is answered **per lap**, from the share of readable
frames that show water, never from a single sample.

### Guards (rule 10), each for something seen on the calibration video

* **A frame that disagrees with both neighbours is dropped.** A codec glitch
  blanked the fill for five frames while the bracket stayed lit; a real drain
  animates through intermediate levels over ~0.8 s.
* **A dimmed HUD is not a dry reading.** The whole HUD fades at the start and end
  of a clip; frames where the tyre bar is not lit are `cannot see`.
* **The lap's answer needs readings.** Fewer than `MIN_READS` readable frames in a
  lap is `cannot see`, never `dry` (rule 3).

Every threshold here comes from one wet video and one dry race. Levels between 1
and 56 px were never held on it, so the boundary is placed in that gap and **the
pale-below-the-tick / blue-above colour split is not relied on**.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Geometry, in pixels at the 1080p flat HUD, relative to `locate_gauge`'s bars:
# the front-left bar is 36 px tall there, and everything scales with it.
REF_BAR_PX = 36
FILL_X_FROM_FL = (-50, -39)     # fill column x0, x1 relative to fl.x0
FILL_TOP_FROM_FL = 1            # first fill row relative to fl.y0
FILL_BOTTOM_FROM_RL = -3        # last fill row relative to rl.y1
FILL_RANGE_PX = 86              # rows the fill can occupy at REF_BAR_PX

# A row is filled when half its pixels are pale (every channel high) or blue.
PALE_MIN = 150
BLUE_OVER_RED = 60
ROW_FILLED_SHARE = 0.5
# A bar is lit when its white section is bright; below this the HUD is fading.
LIT_MIN = 200

# Wet track read 57-81 px of 86; dry read 0; nothing was held between 1 and 56.
# The boundary sits inside that empty gap, as a share of the fill range.
WET_LEVEL = 0.30
# Share of a lap's readable frames that must show water for the lap to be wet,
# and the share below which it is dry. Between the two the lap is `mixed`: a
# drying line, a tunnel, a shower that started mid-lap.
LAP_WET_SHARE = 0.60
LAP_DRY_SHARE = 0.10
MIN_READS = 5


@dataclass(frozen=True)
class HygroReading:
    level: float | None          # 0..1 of the fill range; None: cannot see
    fill_px: int | None
    why: str = ""

    @property
    def wet(self) -> bool | None:
        return None if self.level is None else self.level >= WET_LEVEL


def _scaled(value: float, scale: float) -> int:
    return int(round(value * scale))


def read_hygrometer(frame, bars: dict | None) -> HygroReading:
    """One frame's reading. `frame` is an HxWx3 array; `bars` is what
    `hud.locate_gauge` returned for that frame (or None)."""
    import numpy as np

    if not bars or "fl" not in bars or "rl" not in bars:
        return HygroReading(None, None, "wear panel not located")
    img = np.asarray(frame).astype(np.int16)
    fx0, fx1, fy0, fy1 = bars["fl"]
    _, _, _, ry1 = bars["rl"]
    bar_px = fy1 - fy0 + 1
    if bar_px <= 0:
        return HygroReading(None, None, "front-left bar has no height")
    scale = bar_px / REF_BAR_PX

    lit = img[fy0:fy1 + 1, fx0:fx1 + 1, :].min(axis=2)
    if lit.size == 0 or float(np.percentile(lit, 75)) < LIT_MIN:
        return HygroReading(None, None, "HUD not lit")

    x0 = fx0 + _scaled(FILL_X_FROM_FL[0], scale)
    x1 = fx0 + _scaled(FILL_X_FROM_FL[1], scale)
    top = fy0 + _scaled(FILL_TOP_FROM_FL, scale)
    bottom = ry1 + _scaled(FILL_BOTTOM_FROM_RL, scale)
    if x0 < 0 or top < 0 or bottom >= img.shape[0] or x1 >= img.shape[1] or bottom <= top:
        return HygroReading(None, None, "hygrometer outside the frame")

    column = img[top:bottom + 1, x0:x1 + 1, :]
    pale = column.min(axis=2) > PALE_MIN
    blue = (column[..., 2] - column[..., 0]) > BLUE_OVER_RED
    filled = ((pale | blue).mean(axis=1) >= ROW_FILLED_SHARE)
    run = 0
    for row in range(filled.shape[0] - 1, -1, -1):
        if not filled[row]:
            break
        run += 1
    span = bottom - top + 1
    return HygroReading(round(run / span, 3), run)


@dataclass
class LapWetness:
    state: str                  # "wet" | "dry" | "mixed" | "cannot see"
    wet_share: float | None
    reads: int                  # readable frames the answer rests on
    dropped: int                # single-frame outliers refused
    unreadable: int


@dataclass
class HygrometerLap:
    """Readings across one lap, and the lap's answer.

    `new_session()` must be called at a session boundary (rule 11): a lap's
    readings belong to that lap and its neighbour filter must not reach across
    into the next session's first frame."""
    readings: list[HygroReading] = field(default_factory=list)

    def add(self, reading: HygroReading) -> None:
        self.readings.append(reading)

    def new_session(self) -> None:
        self.readings.clear()

    def close(self) -> LapWetness:
        levels = [r.level for r in self.readings]
        unreadable = sum(1 for level in levels if level is None)
        seen = [level for level in levels if level is not None]
        kept, dropped = [], 0
        for i, level in enumerate(seen):
            if 0 < i < len(seen) - 1:
                before, after = seen[i - 1], seen[i + 1]
                wet_here = level >= WET_LEVEL
                if (before >= WET_LEVEL) == (after >= WET_LEVEL) != wet_here:
                    dropped += 1
                    continue
            kept.append(level)
        self.readings = []
        if len(kept) < MIN_READS:
            return LapWetness("cannot see", None, len(kept), dropped, unreadable)
        share = sum(1 for level in kept if level >= WET_LEVEL) / len(kept)
        if share >= LAP_WET_SHARE:
            state = "wet"
        elif share <= LAP_DRY_SHARE:
            state = "dry"
        else:
            state = "mixed"
        return LapWetness(state, round(share, 3), len(kept), dropped, unreadable)
