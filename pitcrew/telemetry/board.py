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
  scenery into a run 281 px wide, and on one frame into the whole 1920.
* **Rows cannot be closer together than a flag is tall.** Fence palings and tree
  trunks make a perfectly regular ladder at a 7 px pitch; one at x 1684 in the
  trees beat the real board outright.
* **Gaps inside a flag are expected.** These are Union Jacks and the white of
  the cross is not saturated, so a flag arrives as strips with holes. Requiring
  contiguous rows lost the real board on seven of fourteen frames; what
  separates a flag from a paling is its span, not whether every row is filled.

### 5 Sep 2026 — none of the above had ever been run on a race frame

The counts in this docstring are honest and they are not the whole truth: they
were taken on frames from a REPLAY, and the twenty tests underneath were taken
on frames this module's own fixture drew. Fed 73 frames of the 4 Sep Daytona
race (`2026-09-04 22-12-04.mp4`, 1920x1080), the version described above found
a board on **5**, put the driver's own row on one of its rungs on **5**, framed
a gap on 65 of 146 and found a pit column on **0**. That is the live pit wall's
whole-race silence, reproduced on the bench. `tools/board_bench.py` is that
bench, and it imports these functions rather than reimplementing them, because
a second implementation - `tools/read_replay_board.py`, which reads the same
video perfectly - is exactly what hid this for a fortnight.

The same 73 frames now give **73 ladders, 72 on the board, 72 own rows anchored
to one of their own rungs, 130 gap boxes framed and 8 frames of pit columns**,
and on a fresh 120-frame sample of the same race that nothing here was tuned
against, **119 / 119 / 118 / 226 of 240 / 18** against the old version's
**4 / 3 / 3 / 102 / 0**. It is also 24x faster - 83 ms a frame against 1,991 -
which matters because the pit wall runs it on the worker thread that owes the
wear gauge its readings.

Four things changed, and the four things the old version believed were each
false on the real frames:

* **A flag is not red or blue.** It is saturated colour of any hue - or white,
  because Japan is a disc on a white field. Red-or-blue scored Germany, Belgium
  and Mexico as scenery, which is most of the field.
* **A flag is not a run of one width.** It is a FRACTION of a narrow band. The
  eight flags at x=244 on the t=600 s frame knitted into six blobs of 5, 10,
  10, 12, 12 and 18 px against a height bound that wanted 11.2, so three
  survived, and the column that had been located correctly was thrown away.
* **A candidate column is a run's START, not its width.** Where the panel is
  drawn over grass the flag's run merges rightwards into the grass and comes
  out 200+ px wide; the left edge is a hard boundary and does not move.
* **Rung count alone loses to the scene.** Catch fencing at x=1814 makes an
  eleven-rung ladder at a 21 px pitch. What it does not have is a dark name
  band with one bright plate in it: measured, 0.63-0.92 bright on every rung
  against the board's 0.04-0.08 on seven and 0.50 on the driver's own.

### What is deliberately not here yet

**Reading the digits, and this is now MEASURED rather than expected.** The
glyphs are about 12 px tall at a 1080-row projector. Put through
`hud_digits._match`, the four pieces of a real `+ 2.344` scored 0.690, 0.698,
0.666 and 0.605 against a floor of 0.80, and two of them were a `4` and a `4`
run together into one 16 px piece by the segmentation. So the gap boxes are
framed correctly on 130 of 146 and `read_gaps` returns `None` for every one of
them — which is the right failure, and it is a fault in the digit bank's scale
rather than in the board. The bank was built from pit-lane fuel figures, which
are larger; extending it to this size is the next piece of work and it needs a
labelling pass, not a threshold.

The plan beyond that is temporal rather than optical: a gap moves by less than
half a second between frames, so a reading that jumps is refused rather than
averaged, and one that survives consecutive frames is believed. Same discipline
as `hud.coherent`. Locating comes first because nothing can be read until it is
found.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitcrew.diagnostics import log

_log = log(__name__)

# The plate is near-white and unsaturated; a flag or a red box is not.
PLATE_MIN = 150
PLATE_SPREAD = 40

# A row of the board is about six times wider than it is tall. Bounds are
# generous either side of that because the plate grows a red gap box when the
# driver is not leading, and the name length varies.
ASPECT = (4.0, 12.0)

# A flag is saturated colour; sky, plate and name are not. **Of ANY hue.** The
# first version demanded red or blue because the two flags it was written
# against were a Union Jack and an Australian ensign; on the 4 Sep race that
# same test scored Germany, Belgium and Mexico as scenery.
FLAG_SPREAD = 45
FLAG_CHANNEL_MIN = 70
# ...or a flag is white. Japan is a red disc on a white field and reads 8 px of
# saturated colour inside an 18 px flag - below any height a flag can have. INK
# is colour OR white; the translucent panel it is drawn on is neither, and
# measured down the flag column between rows it sits at 55-73 luminance.
FLAG_INK_LUM = 150
# How much of the probe band a row must fill to be inside a flag. Measured on
# the 4 Sep capture, a flag's own rows fill 0.85-1.00 of it.
FLAG_FILL = 0.30
# ...and this much of that run must be COLOUR rather than merely white. **This
# is what separates a flag from a gap readout**, which is white digits on a
# black bar and lands in the same column: measured over three frames, every gap
# row scored exactly 0.00 against 0.20-0.99 for every flag. Without it the two
# 68 px steps either side of the driver read as rows and the ladder stopped
# there, six rungs short.
FLAG_COLOUR_FILL = 0.10
# A flag is a fraction of the frame height, like every other HUD element. The
# floor is low because a flag arrives partly - Japan's disc is 8 px of an 18 px
# flag at 1080 rows - and the ladder, not the height, is what refuses noise.
FLAG_MIN_FRAC, FLAG_MAX_FRAC = 0.006, 0.030
# The band a candidate column is MEASURED in, as a fraction of frame width. It
# is deliberately narrower than a flag: the measure is a fraction, so the band
# only has to sit inside the flag, and a band wider than the flag dilutes it
# with whatever the panel is drawn over.
PROBE_FRAC = 0.008
# How far two column starts may differ and still be the same column.
COLUMN_SLOP = 2
# Fewer rows than this on a ladder is not a leaderboard.
MIN_LADDER_ROWS = 5
# Rows cannot be closer together than this many flag heights - they would
# overlap. Measured: an 18 px flag on a 40 px pitch is 2.2, and every board on
# file is at least 1.8. Below it the row separators inside the panel alias into
# a ladder at half the true pitch, which is how a real board came back with
# every second rung invented.
PITCH_OVER_FLAG = 1.8
# How many candidate columns are evaluated, most-seen first. The board's column
# ranked 1st-10th on every frame of the 4 Sep capture.
MAX_COLUMNS = 60
# The name band left of the flags, in probe widths, and what counts as bright
# in it.
PANEL_WIDTHS = 6
PANEL_BRIGHT = 180
# **The panel is dark on every row but his, and that is the test that beats the
# scene.** Measured at t=600 s: the real board's name band is 0.04-0.08 bright
# on seven rows and 0.50 on the driver's own; the catch fencing at x 1814 that
# outscored it on rung count is 0.63-0.92 on all eleven. A column with no dark
# panel to its left is not a leaderboard however regular it is.
PANEL_DARK_MAX = 0.35
# What fraction of the ladder's rows must carry ink at an x for that x to be
# inside the flag. Used only to report the flag's true extent once the column
# is chosen; the decision was already made on the probe band.
FLAG_EDGE_FILL = 0.6
# The own row's plate must fill at least this much of the band left of the flag.
PLATE_FILL = 0.25
# How far past the driver's own plate the gap readout reaches, as a fraction of
# the plate's width. Measured on the 4 Sep capture: the plate spans x 40-243
# and the readout ends at 269, which is 0.13 of it; 0.25 leaves margin and the
# longest-run trim in `gap_lines` keeps the extra band from reaching scenery.
GAP_REACH = 0.25

# Blank columns left on each side of the framed gap box, so its ink does not
# touch its own edges.
#
# **Without these the box was refused before it was ever read.** `hud_time`
# refuses a box whose ink touches either edge, and correctly - a clipped time
# parses cleanly as a shorter one, and an eleven-offset sweep across a
# `1:23.456` returned a well-formed wrong 3.456. But the box below is the ink's
# own bounding box, so its left edge sits exactly on the `+` sign and its right
# on the last millisecond digit: the guard fired on every gap box of every
# frame, and `read_gaps` had never returned a number in its life. Measured on
# six boxes across the 4 Sep race, 6 px left and 8 px right clears the guard on
# all six with plate to spare. The guard stays; the box now has room inside it.
GAP_MARGIN_L, GAP_MARGIN_R = 6, 8

# Rows of the plate are broken by the driver's name, which is black ON the
# white plate, so runs are merged across a gap of this many rows.
ROW_MERGE = 12
# ...and columns across this many, for the same reason in the other axis.
COL_MERGE = 6

# **A box shorter than this fraction of a row is a CLIPPED PLATE, not a short
# row** - and the row it is measured against is the ladder's own MEDIAN rung
# gap, never the minimum.
#
# Measured 20 Sep 2026 over 292 frames of the Bathurst race (s204) and 182 of
# Sardegna (s188), `scratchpad/findings/G-bench.md`. The driver's own white
# plate registers as flag colour over its whole height, so `flag_ladder` takes
# TWO rungs out of it - its top and bottom edge, 365 and 396 on the traced
# frame - and never one at its centre, 381. `min` over the consecutive gaps is
# then 31 where the row pitch is 40, `half` is 13 instead of 18, and the box
# comes back **15 px of a 35 px plate**. That is not a cosmetic error: it is
# the height `roster._half` sizes every name crop on the frame from, so the
# own row's ink falls under `NAME_MIN_INK`, its bitmap comes back `None`, and
# the matcher is never even asked. Measured on s204, **81.5% of the frames
# that lost the own row lost it that way** and only 18.5% to geometry; and the
# whole-frame name rate is 47% under a 28 px box against 95% at or above it.
#
# The gaps go with it. `gap_lines` places the two interval boxes at
# `y0 - 0.95h` and `y1 + 0.10h` off the box's own height, so a clipped box
# puts both in the wrong place: **0 of 186 interval boxes on a clipped frame
# ever read a value**, against 53.9% on the rest.
#
# The rung gaps are non-uniform by design - `_ladder` allows two wide steps
# for the gap readouts - and irregular in practice on 49% of s204's frames
# against 5% of s188's, because a seven-car field draws a short board. The
# median is what survives both.
CLIPPED_PLATE = 0.6
# **Two rungs closer together than this fraction of the ladder's own median
# gap are one row, not two cars** - and the row is between them.
#
# GT7 draws the board at a constant pitch, so a step meaningfully under that
# pitch is not a row boundary. What it is, measured, is the driver's own
# white plate: it registers as flag ink over its whole height and comes back
# as its top and bottom edges rather than as one row at its centre.
#
# Measured 21 Sep 2026 over the same frames as `CLIPPED_PLATE`, normalising
# every consecutive step by its own frame's median gap:
#
#   Sardegna (s188), the 163 frames that return exactly the field's 8 rungs
#       1,141 steps, smallest 0.85, three under 0.90
#   Bathurst (s204), the 152 frames that return exactly the field's 7
#         912 steps, 39 under 0.85 - and the low tail piles up on 0.775,
#                                    which is a 31 px plate on a 40 px pitch
#
# So the two populations are separated, and 0.82 sits between them: above
# the plate's own 0.775 and below the smallest step any correctly-read board
# has ever drawn. A pair is folded to its midpoint, which is where the row
# actually is; a run of THREE or more close rungs is left alone and said out
# loud, because that is not a plate and a guess at which two of them to fold
# is rule 3 again.
SPLIT_RUNG = 0.82
# Cumulative since the process started, a log throttle only - as with
# `PLATE_GUARD_COUNTS` above, and for the same reason.
RUNG_MERGE_COUNTS = {"folded": 0, "whole": 0, "refused": 0}
# How far either side of the winning rung the REPAIRED search looks, in median
# rung gaps. Wide enough to contain a whole plate that the strip cut in half,
# narrow enough not to reach the neighbouring row.
PLATE_REACH = 0.75
# How many of each plate-guard decision reach the log before it goes quiet.
#
# **Rule 10's second half: the accepts are logged, not only the refusals.**
# This fault hid for months because nothing counted it - the clipped frames
# produced no gap reading at all, so they left no row in `gap_reads` and were
# invisible to every statistic computed from it. The guard fires on a third
# of the frames at Bathurst, so a line per frame would be the whole log;
# these counts keep rising after the last line and every line carries the
# running total, so the number setting the bar is always in the record.
PLATE_GUARD_LOG_MAX = 20
# ...and after that the tally goes out this often, so the record ends with
# the counts rather than with them frozen where the detail stopped.
PLATE_GUARD_TALLY_EVERY = 500
# Cumulative since the process started, and a LOG THROTTLE only - nothing
# reads these as a measurement of a session, which is why there is no reset
# (rule 11 is about state that gets read as this session's; a throttle that
# prints its own running total cannot be).
PLATE_GUARD_COUNTS = {"fired": 0, "declined": 0, "unresolved": 0}


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


def _masks(frame):
    """`(colour, ink)` for a whole frame, off one pass over the pixels.

    Both in one function because both need the same per-pixel maximum and
    minimum, and on a 1920x1080 frame those two reductions are the whole cost
    of locating the board: computing them twice took `flag_ladder` from 60 ms
    to 758 ms, on the worker thread that also owes the wear gauge its readings.
    Integer sums rather than a mean for the same reason — a mean promotes two
    million pixels to float64.

    **The narrowest types that cannot overflow**, measured 17 Sep 2026 at
    21.9 -> 16.1 ms a 1080p frame with identical masks: `top - bottom` cannot
    go negative, so it stays uint8 where the frame is uint8, and three
    channels sum to at most 765, which int16 holds.
    """
    array = np.asarray(frame)
    red, green, blue = array[..., 0], array[..., 1], array[..., 2]
    top = np.maximum(np.maximum(red, green), blue)
    bottom = np.minimum(np.minimum(red, green), blue)
    spread = (top - bottom if array.dtype == np.uint8
              else top.astype(np.int32) - bottom)
    colour = (spread > FLAG_SPREAD) & (top > FLAG_CHANNEL_MIN)
    lit = (red.astype(np.int32 if array.dtype != np.uint8 else np.int16)
           + green + blue) > 3 * FLAG_INK_LUM
    return colour, colour | lit


def _flag_mask(frame):
    """Pixels that are saturated colour of any hue: flag, and nothing dark.

    **Not red-or-blue.** That test was written against the only two flags on
    the frames it was tuned on and it scored the German, Belgian and Mexican
    flags as scenery on the 4 Sep race, which is most of the field.
    """
    return _masks(frame)[0]


def _ink_mask(frame):
    """Flag colour, or white. What a flag is made of; the panel is neither."""
    return _masks(frame)[1]


def _column_starts(mask, limit: int = MAX_COLUMNS):
    """Where saturated runs BEGIN, most-repeated first: candidate flag columns.

    **A run's start survives what its width does not.** Grouping marks by
    (x, width) was the proposal step and it is the one that lost the board on
    the frames where the panel is drawn over grass: grass is saturated too, so
    the flag's run merges rightwards into it and comes out 200+ px wide, which
    no flag-width bound admits. The flag's LEFT edge is a hard boundary between
    panel and flag and it does not move - measured at x=244 with 51-55 starts
    on all three frames tried, including both merged ones.
    """
    # A start is a set pixel whose left neighbour is clear (or the frame edge).
    # Boolean compare rather than an int8 diff of a padded copy: same starts,
    # 6.8 -> 3.8 ms a 1080p frame.
    rise = np.empty_like(mask, dtype=bool)
    rise[:, 0] = mask[:, 0]
    np.greater(mask[:, 1:], mask[:, :-1], out=rise[:, 1:])
    xs = np.nonzero(rise)[1]
    if len(xs) == 0:
        return []
    seen, counts = np.unique(xs, return_counts=True)
    order = np.argsort(-counts)
    out: list[int] = []
    for index in order:
        if counts[index] < MIN_LADDER_ROWS:
            break
        x = int(seen[index])
        if all(abs(x - kept) > COLUMN_SLOP for kept in out):
            out.append(x)
        if len(out) >= limit:
            break
    return out


def _flag_rows(colour, ink, x0: int, width: int, low: int, high: int):
    """`(centre, height)` for every flag-shaped run in one column band.

    A FRACTION of the band, not a run of one width across it. Real GT7 flags
    are multi-coloured — measured heights of 5, 10, 10, 12, 12 and 18 px for
    one column of eight flags — so a search for horizontal runs of a consistent
    width found three of them and a search for the fraction of the band that is
    flag-coloured finds all eight.
    """
    band = ink[:, x0:x0 + width]
    if band.shape[1] == 0:
        return []
    hot = band.mean(axis=1) > FLAG_FILL
    padded = np.concatenate(([False], hot, [False]))
    edges = np.diff(padded.astype(np.int8))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    colour_band = colour[:, x0:x0 + width]
    out = []
    for start, end in zip(starts, ends):
        height = int(end - start)
        if not low <= height <= high:
            continue
        if colour_band[start:end].mean() < FLAG_COLOUR_FILL:
            continue
        out.append(((int(start) + int(end) - 1) // 2, height))
    return out


def _ladder(ys, min_pitch: int, tol: int = 5, min_rows: int = 2):
    """The longest run of rows at one pitch, allowing two equal wider steps.

    The two wider steps are the gap readouts GT7 draws above and below the
    driver's own row. They are the pitch PLUS a constant - measured at 40 and 68
    - and are equal to each other, because it is the same readout drawn twice.

    Two things here were wrong against real frames and both cost whole boards:

    * **The pitch cannot come from the first two rows.** It was read off the
      pair the run starts on, so a board where the driver sits second - his row
      is preceded by a gap readout, which makes the FIRST step a wide one - had
      its pitch set to 68 and lost every row above him. Five frames of the
      4 Sep race are drawn that way. The pitch is now tried independently of
      where the run starts.
    * **A row that does not fit must be skipped, not fatal.** The walk broke at
      the first non-conforming y, so one spurious detection anywhere inside the
      board truncated it there. Anything closer together than the pitch cannot
      be a rung of this ladder and is stepped over.
    """
    if len(ys) < 2:
        return []
    span = ys[-1] - ys[0]
    ceiling = span / max(1, min_rows - 1)
    pitches = sorted({b - a for index, a in enumerate(ys)
                     for b in ys[index + 1:]
                     if min_pitch <= b - a <= ceiling})
    best: list[int] = []
    for pitch in pitches:
        for start in range(len(ys) - len(best)):
            run, wide = [ys[start]], []
            for y in ys[start + 1:]:
                step = y - run[-1]
                if abs(step - pitch) <= tol:
                    run.append(y)
                elif step < pitch - tol:
                    continue
                elif (pitch < step <= 2.2 * pitch and len(wide) < 2
                      and (not wide or abs(step - wide[0]) <= tol)):
                    run.append(y)
                    wide.append(step)
                else:
                    break
            if len(run) > len(best):
                best = run
    return best


def _panel_shares(frame, x0: int, width: int, ys, half: int):
    """How bright the name band is at each rung, or None where there is none.

    The band is left of the flags and is where the driver's own plate is. On a
    leaderboard it is dark on every row but his; on scenery it is whatever the
    scenery is, which is how catch fencing and sky win a rung count.
    """
    left = max(0, x0 - PANEL_WIDTHS * width)
    if x0 - left < 2 * width:
        return None
    # Only the rows the rungs span - each share is cut from them - rather than
    # a float64 copy of the full height, once per candidate column.
    lo = max(0, min(ys) - half)
    lum = np.asarray(frame)[lo:max(ys) + half, left:x0].mean(axis=2)
    return [float((lum[max(0, y - half) - lo:y + half - lo]
                   > PANEL_BRIGHT).mean())
            for y in ys]


def _flag_extent(ink, x0: int, probe: int, ys, height: int):
    """The flag's true left and right edge, once its column is chosen.

    The decision is made on a probe band narrower than a flag, so the band is
    not the answer: `pit_columns` starts its disc search at the flag's right
    edge and `roster` backs off a whole flag width from its left, and both are
    wrong by the difference if the probe is reported as the flag.
    """
    half = max(2, height // 2)
    low = max(0, x0 - 3 * probe)
    high = min(ink.shape[1], x0 + 5 * probe)
    filled = np.zeros(high - low)
    for y in ys:
        filled += ink[max(0, y - half):y + half + 1, low:high].mean(axis=0)
    filled /= max(1, len(ys))
    # **The seed is the fullest column in the probe band, not its left edge.**
    # A candidate column start is where a SATURATED run begins, and the run
    # that starts there need not be the flag: on the synthetic board the winner
    # started four pixels early, its left edge carried no ink at all, and the
    # extent fell back to reporting the probe band as the flag.
    inside = filled[x0 - low:min(len(filled), x0 - low + probe)]
    if len(inside) == 0 or inside.max() < FLAG_EDGE_FILL:
        return x0, x0 + probe
    left = right = x0 - low + int(np.argmax(inside))
    while left > 0 and filled[left - 1] >= FLAG_EDGE_FILL:
        left -= 1
    while right + 1 < len(filled) and filled[right + 1] >= FLAG_EDGE_FILL:
        right += 1
    return low + left, low + right


def _one_rung_per_row(ys):
    """One rung per row: `(rungs, folded, refused)`.

    **The ladder was returning rungs that are not cars, and 54% of the
    roster's foundings arrived on the frames where it did.** Measured 20 Sep
    2026 over 292 frames of Bathurst against a seven-car field
    (`scratchpad/findings/G-bench.md` §4):

        rows offered   frames   readable rows   foundings   per row
        under 7            68             319          10     0.031
        exactly 7         149             875          51     0.058
        MORE than 7        73             412          73     0.177  - 3x

    A row founds a cluster three times as often on a frame carrying more
    rungs than there are cars, because the surplus rungs are not cars: each
    one is handed to `name_bitmap`, comes back as a bitmap that resembles
    nothing on file, and starts an identity of its own. Sardegna, where only
    4% of frames exceed the field, has no such population.

    This folds the commonest of the two surplus families - the driver's own
    plate arriving as its top and bottom edge instead of as one row. See
    `SPLIT_RUNG` for the two measured distributions that set the threshold.

    **The other family is not treated here, and the reason is a
    measurement.** G-bench attributes the rest to a rung group detached from
    the ladder's body by more than 1.6x the pitch. Normalising every step of
    every frame by its own median gap, a step above 1.6x is not rare on a
    correctly-read board: it is 294 of 1,214 steps on Bathurst's frames at
    or under the field, and 315 of 1,190 on Sardegna's clean ones, sitting
    at 1.70 almost exactly. That is the gap readout GT7 draws above and
    below the driver's own row - the wide step `_ladder` exists to allow -
    and a rule that rejected it would cut nearly every board in half at the
    driver's own row. Detachment is real but it is not separable by step
    size, so nothing is refused on that basis.
    """
    if len(ys) < 3:
        return list(ys), 0, 0
    steps = [ys[index + 1] - ys[index] for index in range(len(ys) - 1)]
    floor = SPLIT_RUNG * sorted(steps)[len(steps) // 2]
    close = [step < floor for step in steps]
    out: list[int] = []
    folded = refused = 0
    index = 0
    while index < len(ys):
        run = 0
        while index + run < len(close) and close[index + run]:
            run += 1
        if run == 1:
            out.append((ys[index] + ys[index + 1]) // 2)
            folded += 1
            index += 2
        elif run > 1:
            # Three or more rungs inside a row is not a plate, and folding
            # some pair of them would be a guess. Rule 3: left as found.
            refused += 1
            out.extend(ys[index:index + run + 1])
            index += run + 1
        else:
            out.append(ys[index])
            index += 1
    return out, folded, refused


def _say_rung_merge(before, after, folded: int, refused: int) -> None:
    """One line per ladder, whichever way it went - rule 10's accepts.

    The plate guard one level down was invisible for a whole race because
    only its refusals could have been logged and nothing logged them. This
    counts the ladders it left alone as well as the ones it folded, and
    every line carries the running totals, so the bar is always in the
    record even after the detail stops printing.
    """
    outcome = "folded" if folded else ("refused" if refused else "whole")
    RUNG_MERGE_COUNTS[outcome] = RUNG_MERGE_COUNTS.get(outcome, 0) + 1
    seen = RUNG_MERGE_COUNTS[outcome]
    if seen > PLATE_GUARD_LOG_MAX:
        decided = sum(RUNG_MERGE_COUNTS.values())
        if decided % PLATE_GUARD_TALLY_EVERY == 0:
            _log.info("board: one rung per row over %d ladders - %d folded, "
                      "%d already whole, %d refused as too crowded to fold",
                      decided, RUNG_MERGE_COUNTS["folded"],
                      RUNG_MERGE_COUNTS["whole"], RUNG_MERGE_COUNTS["refused"])
        return
    last = "" if seen < PLATE_GUARD_LOG_MAX else " (last of these)"
    steps = sorted(before[i + 1] - before[i] for i in range(len(before) - 1))
    median_gap = steps[len(steps) // 2] if steps else 0
    if outcome == "whole":
        _log.info("board: ladder of %d rungs, closest pair %d px against a "
                  "%d px median row (floor %.1f) - one rung a row already "
                  "(%d of these so far)%s",
                  len(before), steps[0] if steps else 0, median_gap,
                  SPLIT_RUNG * median_gap, seen, last)
        return
    if outcome == "refused":
        _log.info("board: ladder of %d rungs carries three or more inside "
                  "one %d px row (floor %.1f) - that is not a split plate "
                  "and which pair to fold would be a guess, so the ladder "
                  "stands as found (%d of these so far)%s",
                  len(before), median_gap, SPLIT_RUNG * median_gap, seen,
                  last)
        return
    _log.info("board: ladder of %d rungs folded to %d - %d pair%s under the "
              "floor of %.1f px on a %d px median row, each one plate read "
              "as its two edges; rungs %s -> %s (%d of these so far)%s",
              len(before), len(after), folded, "" if folded == 1 else "s",
              SPLIT_RUNG * median_gap, median_gap, list(before), list(after),
              seen, last)


def flag_ladder(frame):
    """`(x0, x1, [row centres])` for the country flag column, or None.

    The board's own ruler. Every car has a flag from lap one, so this works
    before anybody has pitted and regardless of what is behind the HUD.

    ### Measured against the race, not against the fixture

    Fed 73 frames of the 4 Sep race capture, the version this replaces found a
    board on 5. It located the flag column correctly - x0=244, width 28 - and
    then threw it away, because it scored a column by knitting single-width
    horizontal runs into blobs and demanding each blob be 0.40 of the flag's
    width tall. Real flags are not one colour: at t=600 s the eight flags in
    that column knitted into six blobs of 5, 10, 10, 12, 12 and 18 px, three
    passed, and two rungs is not a ladder. **The whole design assumed a shape
    GT7 does not draw, and the test suite it passed drew that shape for it.**

    Four things replace it, and each is measured:

    * a **fraction** of a probe band per row, not a run of one width across it;
    * **any hue**, plus white, because Japan is a disc on a white field;
    * a **colour floor inside the run**, which is what tells a flag from the
      white-on-black gap readout drawn in the same column;
    * a **dark name band to the left**, which is what tells a leaderboard from
      catch fencing and sky - the two things that beat it on rung count alone.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        return None
    height, width = frame.shape[0], frame.shape[1]
    low, high = max(3, int(FLAG_MIN_FRAC * height)), int(FLAG_MAX_FRAC * height)
    probe = max(6, int(PROBE_FRAC * width))
    if high < low or width <= probe:
        return None
    colour, ink = _masks(frame)
    best, best_score = None, None
    for x0 in _column_starts(colour):
        if x0 + probe > width:
            continue
        rows = _flag_rows(colour, ink, x0, probe, low, high)
        if len(rows) < MIN_LADDER_ROWS:
            continue
        ys = [row[0] for row in rows]
        heights = sorted(row[1] for row in rows)
        flag_h = heights[len(heights) // 2]
        rungs = _ladder(ys, min_pitch=max(6, int(PITCH_OVER_FLAG * flag_h)),
                        min_rows=MIN_LADDER_ROWS)
        if len(rungs) < MIN_LADDER_ROWS:
            continue
        shares = _panel_shares(frame, x0, probe, rungs, max(3, flag_h // 2))
        if shares is None or float(np.median(shares)) > PANEL_DARK_MAX:
            continue
        # Rung count first, and the driver's own plate as the tie-break: two
        # columns that both look like ladders are separated by which one has a
        # single bright row on an otherwise dark band.
        score = (len(rungs), max(shares) - float(np.median(shares)))
        if best_score is None or score > best_score:
            best, best_score = (x0, probe, rungs, flag_h), score
    if best is None:
        return None
    x0, probe, rungs, flag_h = best
    # One rung per row, AFTER the column is chosen: the score above is a rung
    # count, and folding before it would change which column wins rather than
    # only what the winner reports.
    folded_rungs, folded, refused = _one_rung_per_row(rungs)
    _say_rung_merge(rungs, folded_rungs, folded, refused)
    left, right = _flag_extent(ink, x0, probe, folded_rungs, flag_h)
    return int(left), int(right), folded_rungs


def _own_from_ladder(frame, found) -> tuple[int, int, int, int] | None:
    """The driver's own row, picked out of a known ladder by its bright plate.

    One row's height at a time, in the band left of the flag. Sky is the thing
    that breaks a whole-frame plate search and it is simply not in this picture.

    **The longest run of bright columns, not the first to the last.** That is
    the same guard `_own_row_by_plate` already carries and this path was
    written without it: on the real frames a single bright column at x=0 -
    scenery beside the board, one pixel of it - stretched a plate that starts
    at 39 all the way to the frame edge, and `pit_columns` takes the board's
    left edge as the bound its pit flag is looked for in.

    ### 20 Sep 2026 - the box was a fraction of a row high, and that is what
    ### lost the driver's own name on two frames in five

    The strip is cut from `min` over the rung gaps, and **the driver's own
    white plate registers as flag colour over its whole height**, so the
    ladder takes two rungs out of one plate and the minimum gap is an edge-
    to-edge measurement of the plate rather than the row pitch. The box came
    back 15 px of a 35 px plate, `roster._half` sized every name crop on the
    frame from it, and the own row's bitmap came back `None` - so the identity
    matcher was never asked, on 81.5% of the frames that lost the own row.
    `CLIPPED_PLATE` carries the measurement and the bench that settled it.

    Two halves, and **neither works without the other**: growing the box while
    `roster.read` still asked whether a rung was within 8 px of the box's
    MIDPOINT measured worse than doing nothing (82.9% -> 58.9%), because a box
    grown to the plate moves its own midpoint away from the rung. The other
    half is `roster.py`'s `board[1] <= y <= board[3]`.
    """
    if found is None:
        return None
    flag_x0, _, ys = found
    if len(ys) < 2 or flag_x0 < 20:
        return None
    steps = sorted(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    pitch, median_gap = steps[0], steps[len(steps) // 2]
    half = max(3, int(pitch * 0.45))
    # How far the repair may look, if it is needed. The band is cut to it
    # up front because the repair is cut from the band - see `CLIPPED_PLATE`.
    reach = max(half, int(median_gap * PLATE_REACH))
    # Only the band left of the flag is ever looked at, so only that band is
    # computed: the whole-frame version of these two reductions was 181 ms of
    # the 271 ms this function cost, for pixels it then sliced away.
    # And only the rows the rungs span: every strip below is cut from them.
    lo = max(0, min(ys) - reach)
    band = np.asarray(frame)[lo:max(ys) + reach, :flag_x0]
    bright = ((band.min(axis=2) > PLATE_MIN)
              & (np.ptp(band, axis=2) < PLATE_SPREAD))
    best, score = None, 0.0
    for y in ys:
        strip = bright[max(0, y - half) - lo:y + half - lo]
        if strip.size:
            filled = float(strip.mean())
            if filled > score:
                best, score = y, filled
    if best is None or score < PLATE_FILL:
        return None
    box = _plate_box(bright, lo, best, half, containing=False)
    if box is not None and (box[3] - box[1]) >= CLIPPED_PLATE * median_gap:
        _say_plate_guard("declined", box, best, median_gap, reach, box)
        return box
    # The box is a fraction of a row high, so the strip it was cut from was
    # centred on the wrong y and was too short to hold the plate anyway. Take
    # the lit run the winning rung falls INSIDE, over a strip wide enough to
    # contain a whole row. **`None` where no run contains the rung** - rule 3:
    # a plate that cannot be re-derived is not a plate of some other size.
    repaired = _plate_box(bright, lo, best, reach, containing=True)
    _say_plate_guard("fired" if repaired is not None else "unresolved",
                     box, best, median_gap, reach, repaired)
    return repaired


def _plate_box(bright, lo: int, rung: int, reach: int, *, containing: bool):
    """The driver's plate about one rung, as `(x0, y0, x1, y1)`, or None.

    `containing` is the repair: the lit run the rung falls INSIDE, rather than
    the longest run in the strip. The two differ exactly where they matter -
    a strip centred off the plate's centre clips it, and the longest run in
    that strip is the clipped remnant, while the run containing the rung is
    the plate itself once the strip is wide enough to hold it.

    ### 21 Sep 2026 - the rows are settled first, and the columns are then
    ### measured over THOSE rows rather than over the whole strip

    A column was called lit when it was bright down the entire +-reach strip,
    and `PLATE_REACH` widened that strip to three-quarters of a row either
    side precisely so it could hold a plate the old one cut in half. So on
    the frames the repair exists for, the strip spans the neighbouring rows -
    which are dark - and a column carrying the plate can only score about
    half. Everything fell under the 0.4 floor, `cols` became the longest
    surviving run, and that is the blank margin beside the name rather than
    the plate.

    Measured on the branch's own `SPLIT_RUNGS` fixture, against a plate that
    really spans x 40-243: the box came back `(40, 366, 89, 397)` - right in
    height, **49 px of a 203 px plate** in width. `gap_lines` searches
    `x0 -> x1 + 0.25(x1 - x0)` off that width, so a quartered box puts the
    two interval readouts outside the band: on a real Daytona frame the same
    box returns `(None, None)` where the whole one returns both. The repair
    was working against the gaps it was made to recover.

    The plate's own rows are the only rows a column should be judged on, and
    they are known by the time the columns are wanted - so they are taken
    first. On 290 real s204 frames the box was already narrower than 150 px
    on 8, so this is a tail on the bench and the whole width on the fixture;
    both are the same defect.
    """
    top, bottom = max(0, rung - reach), rung + reach
    strip = bright[top - lo:bottom - lo]
    lit_rows = np.where(strip.mean(axis=1) > 0.4)[0]
    if len(lit_rows) < 3:
        return None
    runs = _runs(lit_rows, ROW_MERGE)
    if containing:
        here = rung - top
        rows = next((run for run in runs if run[0] <= here <= run[-1]), None)
        if rows is None:
            return None
    else:
        rows = max(runs, key=len)
    if len(rows) < 3:
        return None
    # The plate's own rows, not the whole strip - see above.
    plate = strip[rows[0]:rows[-1] + 1]
    lit_cols = np.where(plate.mean(axis=0) > 0.4)[0]
    if len(lit_cols) < 10:
        return None
    cols = max(_runs(lit_cols, COL_MERGE), key=len)
    if len(cols) < 10:
        return None
    return (int(cols[0]), int(top + rows[0]),
            int(cols[-1]), int(top + rows[-1]))


def _say_plate_guard(outcome: str, box, rung: int, median_gap: int,
                     reach: int, repaired) -> None:
    """One line per plate-guard decision, with the numbers that decided it.

    **Both directions, because rule 10 asks for the accepts.** A guard that
    only says when it fires cannot be told apart from one that never runs, and
    a guard that only says when it declines cannot be told apart from one that
    fires on everything. Both go out at INFO and both are throttled at
    `PLATE_GUARD_LOG_MAX` of their own outcome - a decision the log level
    hides is a decision that was not logged, and 20 lines of each is 60 lines
    a race.

    After the cap the tally still goes out every `PLATE_GUARD_TALLY_EVERY`
    decisions, so a long race ends with the three counts in the record rather
    than with the count frozen where the detail stopped printing.
    """
    PLATE_GUARD_COUNTS[outcome] = PLATE_GUARD_COUNTS.get(outcome, 0) + 1
    seen = PLATE_GUARD_COUNTS[outcome]
    if seen > PLATE_GUARD_LOG_MAX:
        decided = sum(PLATE_GUARD_COUNTS.values())
        if decided % PLATE_GUARD_TALLY_EVERY == 0:
            _log.info("board: own-row plate guard over %d frames - "
                      "%d re-derived, %d stood, %d refused outright",
                      decided, PLATE_GUARD_COUNTS["fired"],
                      PLATE_GUARD_COUNTS["declined"],
                      PLATE_GUARD_COUNTS["unresolved"])
        return
    last = "" if seen < PLATE_GUARD_LOG_MAX else " (last of these)"
    floor = CLIPPED_PLATE * median_gap
    was = ("no box at all" if box is None
           else f"a box spanning {box[3] - box[1]} px")
    if outcome == "declined":
        _log.info("board: own row at rung y=%d is %s against a %d px median "
                  "row and a %.1f px floor - not clipped, the plate stands "
                  "(%d of these so far)%s",
                  rung, was, median_gap, floor, seen, last)
        return
    if repaired is None:
        _log.info("board: own row at rung y=%d came back %s against a %d px "
                  "median row (floor %.1f), and no lit run within +-%d px "
                  "contains that rung - no own row this frame rather than a "
                  "guessed one (%d of these so far)%s",
                  rung, was, median_gap, floor, reach, seen, last)
        return
    _log.info("board: own row at rung y=%d came back %s against a %d px "
              "median row (floor %.1f) - re-derived from the run containing "
              "the rung over +-%d px to y %d-%d, spanning %d px "
              "(%d of these so far)%s",
              rung, was, median_gap, floor, reach, repaired[1], repaired[3],
              repaired[3] - repaired[1], seen, last)


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

    **The readout is right-aligned to the FLAG column, not to the plate.**
    Measured on the 4 Sep capture: the driver's plate ends at x 243 and
    `+ 2.344` runs from 216 to 269, so a band bounded by the row's own width
    cut the last two glyphs off. That is not a smaller reading, it is an
    unreadable one — `hud_time` refuses a box whose ink touches an edge — so
    the band reaches `GAP_REACH` of the row's width past it, and the ink is
    then taken as its longest column run rather than first-to-last, because
    a band that reaches past the board can reach into the scenery.
    """
    x0, y0, x1, y1 = row
    height = y1 - y0 + 1
    right = min(frame.shape[1] - 1, int(x1 + GAP_REACH * (x1 - x0)))
    out = []
    for top in (y0 - int(height * 0.95), y1 + int(height * 0.10)):
        top = max(0, top)
        strip = frame[top:top + height, x0:right + 1]
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
        used = np.where(ink.any(axis=0))[0]
        if len(used) < 8:
            out.append(None)
            continue
        cols = max(_runs(used, max(COL_MERGE, height // 3)), key=len)
        rows = np.where(ink[:, cols[0]:cols[-1] + 1].any(axis=1))[0]
        if len(cols) < 8 or len(rows) < 5:
            out.append(None)
            continue
        # Horizontally only. The two boxes sit one row above and one below the
        # driver's own, with about ten pixels between them and it, so vertical
        # margin would reach into the neighbouring row's ink - and the band
        # reader crops to the text's own rows anyway.
        left = max(0, int(x0 + cols[0]) - GAP_MARGIN_L)
        right = min(frame.shape[1] - 1, int(x0 + cols[-1]) + GAP_MARGIN_R)
        out.append((left, int(top + plate[0] + rows[0]),
                    right, int(top + plate[0] + rows[-1])))
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
