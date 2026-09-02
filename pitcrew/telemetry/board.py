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

### The plate is not the landmark. The flag column is.

**Measured over a whole 48-minute race, the plate search found a board on 62 of
162 frames and about half of those were wrong** - boxes at (1680, 0), at
(1312, 412), at (0, 1047), each returned as confidently as a real one. The
cause is bright sky: sky is bright AND unsaturated, so it passes the plate test,
and once it does the longest-run scan merges every row into one blob.

A country flag cannot be imitated by sky. It is saturated colour, in a
rectangle, one per row, at a constant pitch - and it is drawn for every car
from lap one, unlike the compound disc which appears only in the pit lane. So
the board is found from the flags first and the plate is used only to say WHICH
row is the driver's, inside a strip one row high where sky cannot reach.

Over the same 162 frames that finds a board on all of them, and the answers
agree with each other: 161 boards at x 250-275, 159 with exactly eight rows,
pitch 39-40 on 160. The plate scan is kept as a fallback for a board drawn
without flags, and where both succeed their boxes agree within a few pixels.

Four things had to be measured rather than assumed, and each was a bug first:

* **The wide steps are pitch PLUS a constant, not a doubled pitch.** GT7 inserts
  a gap readout above and below the driver's own row. At 1440p the pitch is 40
  and those two steps are 68. Modelling them as 2x40 threw away every row past
  the driver.
* **A column run is not a flag column.** At Spa the flags merge with saturated
  scenery into a run 281 px wide, and on one frame into the whole 1920. Flags
  are found as marks that share an x, share a width and land on a pitch - the
  same three-way agreement `pit_columns` uses for the compound disc.
* **Rows cannot be closer together than a flag is wide.** Fence palings and tree
  trunks make a perfectly regular ladder at a 7 px pitch; one at x 1684 in the
  trees beat the real board outright.
* **Gaps inside a flag are expected.** These are Union Jacks and the white of
  the cross is not saturated, so a flag arrives as strips with holes. Requiring
  contiguous rows lost the real board on seven of fourteen frames; what
  separates a flag from a paling is its span, not whether every row is filled.

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

# A flag is saturated colour; sky, plate and name are not.
FLAG_SPREAD = 45
FLAG_LEAD, FLAG_CHANNEL_MIN = 25, 70
# A flag is a fraction of the frame height, like every other HUD element.
MARK_MIN_FRAC, MARK_MAX_FRAC = 0.012, 0.060
# How far two marks may differ in x, or in width, and still be one column.
MARK_SLOP = 4
# Fewer rows than this on a ladder is not a leaderboard.
MIN_LADDER_ROWS = 5
# A flag is at least this fraction of its own width tall. A fence paling is not.
FLAG_SQUAT = 0.40
# The own row's plate must fill at least this much of the band left of the flag.
PLATE_FILL = 0.25

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


def _flag_mask(frame):
    """Pixels that are saturated red or blue: flag colour, and nothing else."""
    red, blue = frame[..., 0], frame[..., 2]
    saturated = (frame.max(axis=2) - frame.min(axis=2)) > FLAG_SPREAD
    coloured = (((blue > red + FLAG_LEAD) & (blue > FLAG_CHANNEL_MIN))
                | ((red > blue + FLAG_LEAD) & (red > FLAG_CHANNEL_MIN)))
    return saturated & coloured


def _marks(mask, low: int, high: int):
    """Horizontal runs of flag colour of plausible flag width, as (y, x, w)."""
    padded = np.zeros((mask.shape[0], mask.shape[1] + 2), dtype=bool)
    padded[:, 1:-1] = mask
    edges = np.diff(padded.astype(np.int8), axis=1)
    rows, starts = np.where(edges == 1)
    _, ends = np.where(edges == -1)
    out = []
    for y, x0, x1 in zip(rows, starts, ends):
        width = int(x1 - x0)
        if low <= width <= high:
            out.append((int(y), int(x0), width))
    return out


def _ladder(ys, min_pitch: int, tol: int = 5):
    """The longest run of rows at one pitch, allowing two equal wider steps.

    The two wider steps are the gap readouts GT7 draws above and below the
    driver's own row. They are the pitch PLUS a constant - measured at 40 and 68
    - and are equal to each other, because it is the same readout drawn twice.
    """
    best = []
    for start in range(len(ys)):
        for nxt in range(start + 1, len(ys)):
            pitch = ys[nxt] - ys[start]
            if pitch < min_pitch:
                continue
            run, wide = [ys[start], ys[nxt]], []
            for y in ys[nxt + 1:]:
                step = y - run[-1]
                if abs(step - pitch) <= tol:
                    run.append(y)
                elif (pitch < step <= 2.2 * pitch and len(wide) < 2
                      and (not wide or abs(step - wide[0]) <= tol)):
                    run.append(y)
                    wide.append(step)
                else:
                    break
            if len(run) > len(best):
                best = run
    return best


def flag_ladder(frame):
    """`(x0, x1, [row centres])` for the country flag column, or None.

    The board's own ruler. Every car has a flag from lap one, so this works
    before anybody has pitted and regardless of what is behind the HUD.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    height = frame.shape[0]
    low, high = int(MARK_MIN_FRAC * height), int(MARK_MAX_FRAC * height)
    if low < 1:
        return None
    found = _marks(_flag_mask(frame), low, high)
    if len(found) < MIN_LADDER_ROWS:
        return None
    best = None
    for _, x0, width in found:
        group = sorted({m[0] for m in found
                        if abs(m[1] - x0) <= MARK_SLOP
                        and abs(m[2] - width) <= MARK_SLOP})
        if len(group) < MIN_LADDER_ROWS:
            continue
        knit = max(3, width // 2)
        blobs, run = [], [group[0]]
        for y in group[1:]:
            if y - run[-1] <= knit:
                run.append(y)
            else:
                blobs.append(run)
                run = [y]
        blobs.append(run)
        centres = [int((b[0] + b[-1]) / 2) for b in blobs
                   if (b[-1] - b[0] + 1) >= FLAG_SQUAT * width]
        if len(centres) < MIN_LADDER_ROWS:
            continue
        rungs = _ladder(centres, min_pitch=max(6, int(0.9 * width)))
        if len(rungs) < MIN_LADDER_ROWS:
            continue
        if best is None or len(rungs) > len(best[2]):
            best = (int(x0), int(x0 + width), rungs)
    return best


def _own_from_ladder(frame, found) -> tuple[int, int, int, int] | None:
    """The driver's own row, picked out of a known ladder by its bright plate.

    One row's height at a time, in the band left of the flag. Sky is the thing
    that breaks a whole-frame plate search and it is simply not in this picture.
    """
    if found is None:
        return None
    flag_x0, _, ys = found
    if len(ys) < 2 or flag_x0 < 20:
        return None
    pitch = min(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    half = max(3, int(pitch * 0.45))
    bright = ((frame.min(axis=2) > PLATE_MIN)
              & (np.ptp(frame, axis=2) < PLATE_SPREAD))
    best, score = None, 0.0
    for y in ys:
        strip = bright[max(0, y - half):y + half, :flag_x0]
        if strip.size:
            filled = float(strip.mean())
            if filled > score:
                best, score = y, filled
    if best is None or score < PLATE_FILL:
        return None
    top, bottom = max(0, best - half), best + half
    strip = bright[top:bottom, :flag_x0]
    rows = np.where(strip.mean(axis=1) > 0.4)[0]
    cols = np.where(strip.mean(axis=0) > 0.4)[0]
    if len(rows) < 3 or len(cols) < 10:
        return None
    return (int(cols[0]), int(top + rows[0]),
            int(cols[-1]), int(top + rows[-1]))


def own_row(frame, ladder=None) -> tuple[int, int, int, int] | None:
    """The driver's own row, or None.

    The flag ladder first, because the plate alone cannot tell a leaderboard
    from a bright sky; the plate scan as a fallback, for a board drawn without
    flags. `frame` is an RGB array of the whole capture. Never raises.

    `ladder` is `flag_ladder(frame)`. Pass it wherever the caller already has
    one: finding it is an O(n^2) scan over every saturated run in the frame,
    and on a track with red kerbs and coloured cars that is thousands of runs.
    A live sampler that located the board once and then let this locate it
    again would be paying for it twice on the worker thread that owes the wear
    gauge its readings.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    if ladder is None:
        ladder = flag_ladder(frame)
    by_flags = _own_from_ladder(frame, ladder)
    if by_flags is not None:
        return by_flags
    return _own_row_by_plate(frame)


def _own_row_by_plate(frame) -> tuple[int, int, int, int] | None:
    """The original locator: the one bright plate among dark rows.

    Kept as a fallback and no longer the first answer. On a real race it finds
    a board on about two frames in five and is wrong on roughly half of those,
    because sky satisfies every test it makes.
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
