"""Contact damage, read off the car icon on the HUD wear panel - plan row 5.20.

The driver, 14 Sep 2026, with a screenshot: *"you can also see damage to rear of
car"*. GT7 draws a small top-down car between the two columns of wear bars, and
the end of it that was hit turns red.

### What it is, measured on 14 Sep 2026

Session 166 (Suzuka race, flat 1080p): two episodes, and 621 clean lit frames
across sessions 158-160, 164-166 and the 14 Sep replay.

* **Only the bumper arc of the end that was hit turns red.** Rear contact on lap
  2 lit the rear arc from 288 s to 381 s; an off on lap 10 lit the front arc from
  ~1266 s to 1401 s. Rails, wheel triangles and body stayed grey both times.
* **The clean icon carries no red at all**: 0 red pixels on every part of every
  one of the 621 clean frames. Lit arcs carried 22-52.
* **It pulses about twice a second, and the onset is the weak part.** Once an
  episode is established a frame at this threshold reads it clear rarely (rear
  3 of 103, front 20 of 136) - but for the first ~10-15 s after the front hit
  the arc read 0 px on most 1 s samples, with single lit frames between. A
  single clear read is never "no contact"; `HudSession.contact_recent` is what
  may say that, and it states the onset latency.
* **It clears on its own**, after 90-135 s, with no pit stop: a fade to pink for
  about a second, then grey. So this reads **recent contact**, not damage that
  waits for a repair, and nothing downstream may treat it as the car's standing
  condition.
* **Red kerbs and pit-lane paint show through the see-through panel.** On the
  icon's own pixels they never passed the red test on the survey frames, but
  they tint several parts at once where damage is confined to one arc - so red
  on the rails, triangles or body refuses the whole frame.

### What it may not claim

**Which corner, or how much.** The arc spans the bumper; left against right was
never lit separately, and "more red" was intensity, not more parts. **Only the
flat 1080p HUD's 36 px bars** were measured - any other size is refused. **The
pit lane was never seen with damage**, and this reader has no pit knowledge, so
red pit paint behind the see-through panel could light an arc during a stop;
a consumer must not read contact in the lane.

**Calibrated on recordings, not on live capture.** Every survey frame is an
ffmpeg decode of an mp4; the live HUD source is an uncompressed grab. Chroma
subsampling blurs a 2-3 px red stroke, so arc counts, the clean zero and kerb
bleed may differ live. **Nothing consumes this until a live grab with contact
has been checked** (plan row 5.20).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

BANK_PATH = Path(__file__).with_name("hud_damage_mask.json")

# The red test the survey used: saturated red, well clear of green and blue.
RED_MIN = 150
RED_OVER = 60
# An arc is lit on this many red pixels. Clean frames: 0; lit arcs mostly
# 22-52, and 20 of 136 front-episode reads below 8.
MIN_ARC_PX = 8
# Any red pixel on the icon's own rails, triangles or body refuses the frame.
MAX_GUARD_PX = 0
SIZE_TOLERANCE = 0.08
REAR_OFFSET_TOLERANCE = 1
# The four bars must sit where the panel puts them, or the icon is not where
# the mask looks: rear-left under front-left, front-right 84 px across
# (survey: 80-88 on all but 3 of 1030 frames).
COLUMN_X_TOLERANCE = 3
FR_FROM_FL_X0 = 84
FR_X_TOLERANCE = 4


@dataclass(frozen=True)
class DamageRead:
    """One frame. `front`/`rear` True: that arc is lit NOW. False: not lit in
    this frame, which inside an episode is the dim half of the pulse. None:
    the frame could not be read, with `why`."""
    front: bool | None
    rear: bool | None
    front_px: int | None = None
    rear_px: int | None = None
    why: str = ""


@lru_cache(maxsize=1)
def _bank() -> dict:
    data = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    for part in ("front_arc", "rear_arc", "guard"):
        cells = np.asarray(data[part], dtype=int)
        data[part] = (cells[:, 0], cells[:, 1])
    return data


def read_damage(frame, bars: dict | None) -> DamageRead:
    """Which bumper arc is lit on one frame, or None with the reason."""
    if not bars or "fl" not in bars or "rl" not in bars:
        return DamageRead(None, None, why="wear panel not located")
    bank = _bank()
    fx0, _, fy0, fy1 = bars["fl"]
    ry1 = bars["rl"][3]
    bar_px = fy1 - fy0 + 1
    if abs(bar_px / bank["ref_bar_px"] - 1.0) > SIZE_TOLERANCE:
        return DamageRead(None, None, why=f"bars are {bar_px} px; the icon was "
                                          f"measured at {bank['ref_bar_px']}")
    if abs((ry1 - fy0) - bank["rear_bar_bottom_from_fl_y0"]) > REAR_OFFSET_TOLERANCE:
        return DamageRead(None, None, why="front and rear bars are not the "
                                          "measured panel apart")
    if (abs(bars["rl"][0] - fx0) > COLUMN_X_TOLERANCE
            or ("fr" in bars and abs(bars["fr"][0] - fx0 - FR_FROM_FL_X0)
                > FR_X_TOLERANCE)):
        return DamageRead(None, None, why="the bars are not in the measured "
                                          "columns, so the icon is not placed")
    pixels = np.asarray(frame)
    (top, bottom), (left, right) = bank["window"]["dy"], bank["window"]["dx"]
    y0, x0 = fy0 + top, fx0 + left
    if (y0 < 0 or x0 < 0 or fy0 + bottom > pixels.shape[0]
            or fx0 + right > pixels.shape[1]):
        return DamageRead(None, None, why="icon runs off the frame")
    # Crop before widening the type: only a 117 x 111 window is ever read.
    crop = pixels[y0:fy0 + bottom, x0:fx0 + right, :3].astype(np.int16)
    r, g, b = crop[..., 0], crop[..., 1], crop[..., 2]
    red = (r > RED_MIN) & (r - g > RED_OVER) & (r - b > RED_OVER)

    def count(part: str) -> int:
        ys, xs = bank[part]
        return int(red[ys - top, xs - left].sum())

    guard = count("guard")
    if guard > MAX_GUARD_PX:
        return DamageRead(None, None, why=f"red on {guard} px outside the "
                                          f"bumper arcs - background showing through")
    front, rear = count("front_arc"), count("rear_arc")
    return DamageRead(front >= MIN_ARC_PX, rear >= MIN_ARC_PX, front, rear)
