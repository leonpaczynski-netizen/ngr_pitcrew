"""Finding the race leaderboard on screen, and the three gaps on it.

He left VR on 2 Sep 2026 and the race HUD went back into screen space, which
put the pit wall in reach for the first time: his position and field size, the
top three, a window of drivers around him, and — the part no telemetry channel
carries — **the gap to the car ahead, to the leader and to the car behind.**

**Landmarks, never coordinates.** Everything here is anchored to the driver's
own row, which is the one bright plate in the board while every other row is
dark blue. The gap lines then sit at offsets from it. That survives a change of
resolution, of projector size, or of where the board is composited — all three
of which happened within an hour of starting this, and each one broke a version
that trusted a coordinate.

### Three guards, and each one was earned

Every guard below exists because its absence produced a confident wrong answer
on a real frame, which is the failure mode `hud.py` was already carrying:

* **Run length, not fraction.** Rows were first scored by what fraction of the
  search width was bright. Narrowed to the left 23% of the frame the plate
  scored 0.74; widened to the whole frame the same plate scored 0.16 and
  vanished. The plate had not changed, the denominator had. The longest
  consecutive run of bright pixels is a property of the plate alone.
* **The longest contiguous column run, not first-to-last.** At the plate's
  rows the frame also holds bright sky on the far side of the screen, so
  spanning the first qualifying column to the last measured 1780 px and the
  real plate failed its own size guard.
* **Aspect.** A width bound loose enough to survive magnification is loose
  enough to admit the whole top bar of the HUD: on a live frame it returned an
  899x46 band across POSITION and LAP as the driver's row. A leaderboard row is
  about six times wider than tall however it is drawn; that band was 19.5.
  Shape is the thing that does not change.

### What is deliberately not here yet

**Reading the digits.** The glyphs are about 12 px tall at a 1080-row
projector, which is marginal for a template match in isolation — so the plan is
temporal rather than optical: a gap moves by less than half a second between
frames, so a reading that jumps is refused rather than averaged, and one that
survives consecutive frames is believed. Same discipline as `hud.coherent`.
Locating comes first because nothing can be read until it is found.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# The plate is near-white and unsaturated; a flag or a red box is not.
PLATE_MIN = 150
PLATE_SPREAD = 40

# A row of the board is about six times wider than it is tall. Bounds are
# generous either side of that because the plate grows a red gap box when the
# driver is not leading, and the name length varies.
ASPECT = (4.0, 12.0)

# Rows of the plate are broken by the driver's name, which is black ON the
# white plate, so runs are merged across a gap of this many rows.
ROW_MERGE = 12
# ...and columns across this many, for the same reason in the other axis.
COL_MERGE = 6


@dataclass(frozen=True)
class Board:
    """Where the driver's own row is, and the three gap readouts on it.

    Boxes are `(x0, y0, x1, y1)` inclusive. `None` for a gap that is not drawn
    — which is a real state: there is no car ahead of the leader, none behind
    the last driver, and GT7 renders `--:--.---` at the start of a race.
    """
    row: tuple[int, int, int, int]
    ahead: tuple[int, int, int, int] | None
    leader: tuple[int, int, int, int] | None
    behind: tuple[int, int, int, int] | None


def _runs(indices, merge: int):
    """Split a sorted index array into runs, merging gaps up to `merge`."""
    if len(indices) == 0:
        return []
    breaks = np.where(np.diff(indices) > merge)[0]
    out, start = [], 0
    for edge in list(breaks) + [len(indices) - 1]:
        out.append(indices[start:edge + 1])
        start = edge + 1
    return out


def _longest_run(bits) -> np.ndarray:
    """The longest consecutive True run in each row.

    Done with a cumulative trick rather than a Python loop: this runs on every
    grabbed frame and the frame is two million pixels.
    """
    padded = np.zeros((bits.shape[0], bits.shape[1] + 2), dtype=bool)
    padded[:, 1:-1] = bits
    best = np.zeros(bits.shape[0], dtype=int)
    running = np.zeros(bits.shape[0], dtype=int)
    for column in range(padded.shape[1]):
        column_bits = padded[:, column]
        running = np.where(column_bits, running + 1, 0)
        best = np.maximum(best, running)
    return best


def own_row(frame) -> tuple[int, int, int, int] | None:
    """The driver's own row, found by its plate, or None.

    `frame` is an RGB array of the whole capture. Never raises.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    height, width = frame.shape[0], frame.shape[1]
    if height < 40 or width < 100:
        return None
    bright = ((frame.min(axis=2) > PLATE_MIN)
              & (np.ptp(frame, axis=2) < PLATE_SPREAD))

    per_row = _longest_run(bright)
    hot = np.where(per_row > max(40, 0.04 * width))[0]
    if len(hot) < 8:
        return None

    tall = max(8, int(0.012 * height)), int(0.10 * height)
    wide = int(0.05 * width), int(0.60 * width)
    for run in sorted(_runs(hot, ROW_MERGE), key=len, reverse=True):
        if not tall[0] <= len(run) <= tall[1]:
            continue
        hits = np.where(bright[run[0]:run[-1] + 1].mean(axis=0) > 0.5)[0]
        if len(hits) < 20:
            continue
        pieces = _runs(hits, COL_MERGE)
        cols = max(pieces, key=len)
        if len(cols) < 20:
            continue
        span = cols[-1] - cols[0]
        if not wide[0] <= span <= wide[1]:
            continue
        if not ASPECT[0] <= span / max(1, len(run)) <= ASPECT[1]:
            continue
        return int(cols[0]), int(run[0]), int(cols[-1]), int(run[-1])
    return None


def leader_gap(frame, row) -> tuple[int, int, int, int] | None:
    """The red gap-to-leader box on the driver's own row, or None.

    None where he IS the leader — there is no box then, and inventing one is
    how a gap of zero gets written down for a car that has none.
    """
    x0, y0, x1, y1 = row
    reach = int(x1 + 0.6 * (x1 - x0))
    band = frame[y0:y1 + 1, x0:min(frame.shape[1], reach)]
    if band.size == 0:
        return None
    red = ((band[..., 0] > 110)
           & (band[..., 0] > band[..., 1] * 1.8)
           & (band[..., 0] > band[..., 2] * 1.8))
    hits = np.where(red.mean(axis=0) > 0.35)[0]
    if len(hits) < 12:
        return None
    cols = max(_runs(hits, COL_MERGE), key=len)
    if len(cols) < 12:
        return None
    return int(x0 + cols[0]), y0, int(x0 + cols[-1]), y1


def gap_lines(frame, row):
    """`(ahead, behind)` boxes for the two gap numbers, or None each.

    **The dark plate is found before the ink.** The gap number sits on a dark
    semi-transparent bar and the strip around it is whatever the car is driving
    past — sky, grandstand, flags. Thresholding for white across the whole
    strip lights up the sky and returned one "glyph" the width of the row on 52
    of 64 frames.
    """
    x0, y0, x1, y1 = row
    height = y1 - y0 + 1
    out = []
    for top in (y0 - int(height * 0.95), y1 + int(height * 0.10)):
        top = max(0, top)
        strip = frame[top:top + height, x0:x1 + 1]
        if strip.shape[0] < 6 or strip.size == 0:
            out.append(None)
            continue
        dark = (strip.max(axis=2) < 120).mean(axis=1)
        plate = np.where(dark > 0.55)[0]
        if len(plate) < 5:
            out.append(None)
            continue
        inside = strip[plate[0]:plate[-1] + 1]
        ink = inside.min(axis=2) > PLATE_MIN
        cols = np.where(ink.any(axis=0))[0]
        rows = np.where(ink.any(axis=1))[0]
        if len(cols) < 8 or len(rows) < 5:
            out.append(None)
            continue
        out.append((int(x0 + cols[0]), int(top + plate[0] + rows[0]),
                    int(x0 + cols[-1]), int(top + plate[0] + rows[-1])))
    return out[0], out[1]


def find(frame) -> Board | None:
    """Locate the board and its three gaps, or None if the row is not there.

    None rather than a partly-filled `Board`: without the driver's own row
    there is nothing to anchor the gaps to, and a gap read from an unanchored
    guess is worse than no gap at all.
    """
    row = own_row(frame)
    if row is None:
        return None
    ahead, behind = gap_lines(frame, row)
    return Board(row=row, ahead=ahead, leader=leader_gap(frame, row),
                 behind=behind)
