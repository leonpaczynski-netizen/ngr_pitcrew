"""The pit columns on the race leaderboard: who has stopped, on what, with how much.

GT7 draws three extra columns on a leaderboard row once that car has entered
the pit lane, and they are exactly the pit wall:

* a **pit flag** — a small bright box to the left of the position number;
* a **compound disc** — a saturated red circle with a letter in it;
* a **fuel figure** — a pump icon and a number, which is both litres and
  percent because every GT7 tank is 100 L.

**And the fuel figure is live.** Read across one stop in the Spa replay of
1 Sep 2026 it climbs as the tank fills, so entry fuel, the fill in progress and
exit fuel are all observable from the screen:

    23:06   CruisingChaos 10   Rocky  8
    23:30                 33          22   Beeni 19
    23:54                 57          46         27
    24:36                 93          88         69

That also confirms the refuel rate a third way, independently of the tank
telemetry and of the frame-derived figure: 10 to 33 in 24 s is 0.96 L/s, and
33 to 57 in 24 s is 1.00.

### Why the disc is the anchor

The columns are found from the compound discs rather than from the rows,
because a saturated red square repeated at one x is the most distinctive thing
on the screen — and because it self-validates. A first attempt matched red
anywhere and returned the pit crew's gloves, shoes and helmets: measured on one
frame it produced twelve candidates of which four were real. **The four real
ones were all 28x28 at x 291-318; the eight false ones agreed with each other
about nothing.** So a candidate is only accepted as part of a column that
shares an x and a size with at least one other, which no scatter of scenery
ever does.

### The columns mean "in the lane NOW", not "has stopped"

**Measured across the whole 48-minute Spa replay, and it corrects the reading
this module was built on.** The obvious assumption - that a car which has been
to the pits keeps its columns for the rest of the race - is wrong. Of 94 clean
frames after CruisingChaos filled from 10 L to 89, exactly one showed pit
columns, and that one belonged to A.Maidment, who was in the lane at that
moment showing 2 L. CruisingChaos had none. The earlier evidence that looked
like persistence - 10, 33, 57, 93 - sits entirely inside a 90-second window,
which is the duration of his stop.

That makes this a **stop detector** rather than a fuel history, and it is the
more useful of the two: columns appearing on a rival's row is the event
`race/rival_calls.py` needs, at the moment it can still be acted on. It also
means entry fuel must be caught while the car is standing, because it will not
be there afterwards - so the sampler has to be running, not asked later.

### Given the board's rows, look for a disc ON each one

**The disc-first search loses the driver's own stop, every time.** It finds red
row-runs with `red.any(axis=1)`, which asks whether ANY pixel in a full 1920-px
row is red - so a brake light, a marshal's jacket or a kerb at the far side of
the screen joins that row to its neighbours, and the merged run fails the
disc-height bound. Measured across the window in which he actually pitted at
Spa, his own disc was plainly there - saturated red at x 288-322, RGB (220,
23, 6) - and was never once returned. Rivals came back on the same frames,
because their rows happened not to have scenery beside them.

That mattered more than a missing rival: `race/rivals.fuel_swing` exists to
weigh HIS stop against theirs, and it could be given their half and never his.

So where the caller can say where the board's rows are - `board.flag_ladder`
now can, on every frame of a measured race - the search is inverted. Each known
row is asked whether it carries a disc, in the narrow band right of the flag.
Nothing is inferred from the discs, so nothing is lost when scenery drowns
them, and the guards that existed only to FIND the board from its discs are not
needed on that path.

### Only the top eight rows exist

Every clean frame of that race carried eight rows, positions 1 to 8, with the
driver's own row among them wherever he was running. A rival outside the top
eight is not on the board at all, so nothing here can see him - which bounds
what `race/teammate.py` can say about a teammate who is running ninth.

### What this does not do yet

It does not read the fuel digits. It locates the box they are in. The pit flag
needs no reading at all — its presence IS the fact — so `has_pitted` is usable
today, and that alone tells the engineer who has stopped and who has not.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitcrew.telemetry.board import _runs

# A compound disc is a saturated red circle with a DARK letter in it - see
# `telemetry/compound.py`, which reads that letter. (This said "white" for a
# while, which is wrong and was also stale: the next lines say the loose bounds
# it was justifying were measured and rejected.)
#
# **The disc colour IS the compound**, and there are five of them. Given by the
# driver, 3 Sep 2026, from GT7's timing totem:
#
#     red (S) soft      yellow (M) medium     white (H) hard
#     blue (W) wet      green (I) intermediate
#
# This searched for red alone until then, because every disc in the archive was
# (200, 25, 0) - the whole field ran Racing Soft, so the footage could not
# reveal the rest. The cost of that was not an unread letter but the whole
# stop: a disc of another colour was not found, the row yielded no `PitRow`,
# the driver never entered `in_lane` in `race/pit_wall.py`, `has_pitted` stayed
# False for a car standing in its box, and an open visit closed three frames
# later in the middle of its own fill. **The pit wall could only see rivals on
# the same tyre he was.**
#
# **Only the red one is measured.** The other four are built from the driver's
# description of the colour scheme, so their thresholds are wider than red's
# and should be tightened against real pixels the first time each is seen.
# `telemetry/compound.py` reads the letter as corroboration.
#
# **White is the awkward one** and is why the shape and position guards matter
# more than the colour: a white disc has the same signature as the leaderboard
# plate and the fuel digits. It is separated by being round, disc-sized, and
# the leftmost such blob in the band right of the flag.
# **Strict, and the loose version was tried and was worse.** The HUD is
# semi-transparent, so a pit crew in fluorescent green standing behind the
# leaderboard washes the discs out and they are missed. Relaxing the ratio to
# 1.30 to recover them was measured: it rescued nothing and took false
# positives on the no-pit frames from 2 to 26, because every loosening admits
# far more scenery than HUD. **Missing a frame is the right failure here** —
# the fuel figure is on screen for the whole of a stop, so a frame lost to an
# obscured HUD costs nothing, and a wrong rival fuel figure costs a stop call.
DISC_MIN = 130
DISC_RATIO = 2.0
# A white (hard) disc is bright and unsaturated. Wider than the plate test in
# `board.py` on purpose - this one is bounded by being round and disc-sized in
# a band one flag-width wide, where the plate and the name are not.
WHITE_DISC_MIN, WHITE_DISC_SPREAD = 170, 40

# Discs are square to within antialiasing, and a column of them shares an x.
DISC_SQUARENESS = 0.65, 1.55

# **And a disc is a CIRCLE, which is what admits white safely.** A filled
# circle fills pi/4 = 0.785 of its bounding box, and the two real discs on a
# measured Spa frame came out at 0.780 and 0.798. The false positives the
# white branch let in - scenery behind the translucent HUD, and the fuel
# digits, both bright and unsaturated like a hard-compound disc - measured
# 0.091, 0.224, 0.456 and 0.639. Nothing else in that band is round.
#
# **Measured on the disc's OUTLINE, not on its ink** (`_outline_fill`). The
# bound was calibrated on two red "S" discs and nothing else, and it scored
# the ink - so the dark letter printed on the disc counted as a hole in it.
# An "M" is more ink than an "S": every medium disc in Sardegna Rd 9
# (session 188) scored 0.665-0.694 and was refused. The wall then saw no
# column on any car on medium tyres, which was most of the field - Rocky's
# stop and Boxhead's were never filed at all, and J.jonas's was filed from
# the middle of his fill. Scored on the outline the same discs read
# 0.761-0.791; scenery on quiet frames still reads 0.36-0.42 and 0.98-1.00,
# and the fuel digits beside a disc are refused on height before they get
# here. Every letter now scores what the geometry says a circle scores.
DISC_ROUNDNESS = 0.70, 0.90


def _outline_fill(box) -> float:
    """How much of `box` a shape covers, with the holes inside it filled.

    Each row is counted from its first set pixel to its last, so a letter
    printed on a disc - which is the disc's colour's absence, not its edge -
    stops reading as missing disc. A filled circle scores pi/4 whatever is
    written on it, which is what `DISC_ROUNDNESS` was always meant to test.
    """
    if not box.size:
        return 0.0
    covered = 0
    for row in box:
        on = np.flatnonzero(row)
        if on.size:
            covered += int(on[-1] - on[0] + 1)
    return covered / float(box.size)
COLUMN_SLOP_PX = 4

# A disc is a fraction of the frame height, not a fixed size — the HUD scales.
DISC_MIN_FRAC, DISC_MAX_FRAC = 0.015, 0.055

# The fuel figure sits to the right of the disc, about three disc-widths of
# room. Expressed in disc widths so it survives a resolution change.
FUEL_GAP_W, FUEL_SPAN_W = 0.35, 3.2


@dataclass(frozen=True)
class PitRow:
    """One leaderboard row that carries the pit columns.

    `fuel_box` is where the number is, not the number: reading the digits is
    separate work and a box is not a reading. `None` everywhere means the
    column was not drawn, which for `has_pitted` is itself the fact.
    """
    disc: tuple[int, int, int, int]
    fuel_box: tuple[int, int, int, int] | None
    has_pitted: bool

    @property
    def y(self) -> int:
        """Vertical centre, for matching against a leaderboard row."""
        return (self.disc[1] + self.disc[3]) // 2


def disc_mask(frame):
    """Pixels that could be a compound disc, in any of the five colours.

    Red is the measured one. The rest come from the driver's account of GT7's
    timing totem and are deliberately looser, because a missed disc costs a
    whole stop while a false one is caught by the shape and position guards.
    """
    red, green, blue = frame[..., 0], frame[..., 1], frame[..., 2]
    brightest = frame.max(axis=2)
    spread = brightest - frame.min(axis=2)
    return (
        # red (S) - measured at (200, 25, 0)
        ((red > DISC_MIN) & (red > green * DISC_RATIO)
         & (red > blue * DISC_RATIO))
        # yellow (M) - red and green together, little blue
        | ((red > DISC_MIN) & (green > DISC_MIN)
           & (red > blue * DISC_RATIO) & (green > blue * DISC_RATIO))
        # green (I)
        | ((green > DISC_MIN) & (green > red * DISC_RATIO)
           & (green > blue * DISC_RATIO))
        # blue (W)
        | ((blue > DISC_MIN) & (blue > red * DISC_RATIO)
           & (blue > green * DISC_RATIO))
        # white (H) - bright and unsaturated, which is also the plate and the
        # fuel digits, so this one leans entirely on shape and position.
        | ((brightest > WHITE_DISC_MIN) & (spread < WHITE_DISC_SPREAD))
    )


def _candidates(frame) -> list[tuple[int, int, int, int]]:
    red = disc_mask(frame)
    height = frame.shape[0]
    low, high = DISC_MIN_FRAC * height, DISC_MAX_FRAC * height
    out = []
    for run in _runs(np.where(red.any(axis=1))[0], 3):
        tall = len(run)
        if not low <= tall <= high:
            continue
        cols = np.where(red[run[0]:run[-1] + 1].any(axis=0))[0]
        if len(cols) == 0:
            continue
        for piece in _runs(cols, 4):
            wide = len(piece)
            if not low <= wide <= high:
                continue
            if not DISC_SQUARENESS[0] <= wide / tall <= DISC_SQUARENESS[1]:
                continue
            box = red[run[0]:run[-1] + 1, piece[0]:piece[-1] + 1]
            fill = _outline_fill(box)
            if not DISC_ROUNDNESS[0] <= fill <= DISC_ROUNDNESS[1]:
                continue
            out.append((int(piece[0]), int(run[0]),
                        int(piece[-1]), int(run[-1])))
    return out


def _column(found):
    """Keep only discs that share an x and a size with another.

    **This is the whole guard.** Scenery red — gloves, shoes, brake lights —
    is square and disc-sized often enough to pass the shape test on its own; it
    is never square, disc-sized AND stacked in a column with a twin.
    """
    if len(found) < 2:
        return []
    # **Every candidate group is pitch-checked, not just the biggest.** An
    # earlier version picked the largest group by count and only then tested
    # its spacing, so a scatter of scenery that happened to be numerous
    # displaced the real column before it was ever looked at.
    best = []
    for anchor in found:
        width = anchor[2] - anchor[0]
        group = [d for d in found
                 if abs(d[0] - anchor[0]) <= COLUMN_SLOP_PX
                 and abs((d[2] - d[0]) - width) <= COLUMN_SLOP_PX]
        kept = _on_a_pitch(sorted(group, key=lambda d: d[1]))
        if len(kept) > len(best):
            best = kept
    return best


def _on_a_pitch(column):
    """Keep only discs whose spacing is a multiple of one row pitch.

    **The guard that separates a leaderboard from a scene.** Leaderboard rows
    sit at a fixed pitch, so the vertical gaps between discs are that pitch or
    a small multiple of it — a car with no stop leaves a hole, never a
    fractional offset. Red scenery that happens to be square, disc-sized and
    vertically aligned still lands at arbitrary gaps: measured on a Daytona
    frame where nobody had pitted, two false discs survived every other test
    and were thrown out here.
    """
    if len(column) < 2:
        return []
    gaps = [column[i + 1][1] - column[i][1] for i in range(len(column) - 1)]
    pitch = min(gaps)
    if pitch < 8:
        return []
    kept = [column[0]]
    for disc, gap in zip(column[1:], gaps):
        multiple = gap / pitch
        if abs(multiple - round(multiple)) <= 0.18 and round(multiple) <= 6:
            kept.append(disc)
    return kept if len(kept) >= 2 else []


def _fuel_box(frame, disc):
    """The box the fuel figure sits in, right of the disc, or None."""
    x0, y0, x1, y1 = disc
    width = x1 - x0 + 1
    left = int(x1 + FUEL_GAP_W * width)
    right = int(x1 + FUEL_SPAN_W * width)
    if right >= frame.shape[1] or left >= right:
        return None
    patch = frame[y0:y1 + 1, left:right]
    if patch.size == 0:
        return None
    ink = patch.min(axis=2) > 150
    cols = np.where(ink.any(axis=0))[0]
    rows = np.where(ink.any(axis=1))[0]
    if len(cols) < 4 or len(rows) < 4:
        return None
    return (int(left + cols[0]), int(y0 + rows[0]),
            int(left + cols[-1]), int(y0 + rows[-1]))


def _pit_flag(frame, disc, board_left: int) -> bool:
    """Whether the bright pit box is drawn left of the position number.

    Looks only in the strip left of the board, so a white plate on the row
    itself — the driver's own highlight — cannot be mistaken for it.
    """
    x0, y0, x1, y1 = disc
    right = max(1, board_left)
    strip = frame[y0:y1 + 1, :right]
    if strip.size == 0:
        return False
    bright = (strip.min(axis=2) > 170) & (np.ptp(strip, axis=2) < 45)
    return bool(bright.mean() > 0.25)


def _inside_board(discs, board):
    """Keep a column only where it sits within the leaderboard.

    **The landmark guard, and it is what the others could not do.** Column
    alignment and row pitch are both satisfied by scenery often enough to
    matter: measured over 92 frames in which nobody had pitted, they let 16
    through. A disc belongs to a leaderboard row, so it must sit to the RIGHT
    of the board's left edge and within a couple of row-widths of it. Nothing
    in the scene is constrained that way, and no false positive survived it.
    """
    if board is None:
        return discs
    x0, _, x1, _ = board
    width = max(1, x1 - x0)
    left, right = x0, x0 + int(2.6 * width)
    return [d for d in discs if left <= d[0] <= right]


def _disc_on_row(frame, y: int, left: int, right: int, height: int):
    """A compound disc on one known row, or None.

    The row is given, so this asks only whether the disc is there - which is
    the question the disc-first search could not answer on a row with scenery
    beside it.
    """
    half = max(3, int(height * 0.45))
    top, bottom = max(0, y - half), y + half
    patch = frame[top:bottom, left:right]
    if patch.size == 0:
        return None
    red = disc_mask(patch)
    if not red.any():
        return None
    # **Every candidate blob is tested, and the LEFTMOST disc-shaped one wins.**
    # Taking the longest run was safe while only red was matched; with white in
    # the set the band also contains the fuel digits and whatever bright
    # scenery shows through the HUD, and one of those is often the longer run.
    # On a measured frame that took the disc count from five to two. The disc
    # precedes the fuel figure, so leftmost breaks any remaining tie.
    low, high = DISC_MIN_FRAC * frame.shape[0], DISC_MAX_FRAC * frame.shape[0]
    cols_on = np.where(red.any(axis=0))[0]
    if len(cols_on) == 0:
        return None
    for col_run in _runs(cols_on, 4):
        wide = len(col_run)
        if not low <= wide <= high:
            continue
        strip = red[:, col_run[0]:col_run[-1] + 1]
        rows_here = np.where(strip.any(axis=1))[0]
        if len(rows_here) == 0:
            continue
        for row_run in _runs(rows_here, 3):
            tall = len(row_run)
            if not low <= tall <= high:
                continue
            if not DISC_SQUARENESS[0] <= wide / tall <= DISC_SQUARENESS[1]:
                continue
            box = strip[row_run[0]:row_run[-1] + 1]
            fill = _outline_fill(box)
            if not DISC_ROUNDNESS[0] <= fill <= DISC_ROUNDNESS[1]:
                continue
            return (int(left + col_run[0]), int(top + row_run[0]),
                    int(left + col_run[-1]), int(top + row_run[-1]))
    return None


def read_rows(frame, board, ladder) -> list[PitRow]:
    """Pit columns for a board whose rows are already known.

    `ladder` is `(flag_x0, flag_x1, [row centres])` from `board.flag_ladder`.
    Preferred over `read` wherever it is available: it is the only path that
    returns the driver's own row.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3 or not ladder:
        return []
    flag_x0, flag_x1, ys = ladder
    if len(ys) < 2:
        return []
    height = min(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
    left = flag_x1 + 1
    right = min(frame.shape[1], flag_x1 + 4 * height)
    # **`is not None`, not truthiness.** A board flush against the left edge
    # of the screen has `board[0] == 0`, which is falsy - and that reported
    # "has not pitted" for every car on the frame. The measured Spa boards sit
    # at x 0 whenever the pit flag is drawn, so this was the common case.
    board_left = board[0] if board is not None else None
    out = []
    for y in ys:
        disc = _disc_on_row(frame, y, left, right, height)
        if disc is None:
            continue
        box = _fuel_box(frame, disc)
        if box is None:
            continue
        out.append(PitRow(
            disc=disc, fuel_box=box,
            has_pitted=(_pit_flag(frame, disc, board_left)
                        if board_left is not None else False)))
    return _same_column(out)


def _same_column(rows: list[PitRow]) -> list[PitRow]:
    """Keep only the discs that agree on an x.

    **The one guard from the disc-first path that the row-first path still
    needs.** The rest existed to FIND the board and are redundant now the
    ladder gives it - but discs sharing a column is a fact about the board
    itself, and admitting white cost the search its narrowness: on a measured
    frame two pieces of bright scenery at x 397 came back alongside five real
    discs at 291. Scenery does not line up with a leaderboard column.
    """
    if len(rows) < 2:
        return rows
    tally: dict[int, int] = {}
    for row in rows:
        tally[row.disc[0]] = tally.get(row.disc[0], 0) + 1
    best = max(tally.items(), key=lambda kv: (kv[1], -kv[0]))[0]
    return [row for row in rows if abs(row.disc[0] - best) <= COLUMN_SLOP_PX]


def read(frame, board=None) -> list[PitRow]:
    """Every leaderboard row currently carrying the pit columns.

    Empty where nobody has pitted — which is the ordinary state for the first
    half of a race and is not a failure. `board` is the driver's own row from
    `telemetry.board.own_row`, and without it this is materially less certain:
    it is the only thing that says where the leaderboard IS, and it is also the
    bound on the strip the pit flag is looked for in.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3:
        return []
    if frame.shape[0] < 100 or frame.shape[1] < 200:
        return []
    board_left = board[0] if board else None
    discs = _inside_board(_column(_candidates(frame)), board)
    if len(discs) < 2:
        return []
    # **A disc with no number beside it is not a pit column.** The column
    # exists to carry the fuel figure, so its absence is structural rather
    # than a threshold - which is why this is the guard that finally worked.
    # Colour, size, alignment and row pitch between them still let 15 pieces of
    # scenery through on 92 frames in which nobody had pitted; every one of
    # them had `fuel_box = None`.
    out = []
    for disc in discs:
        box = _fuel_box(frame, disc)
        if box is None:
            continue
        out.append(PitRow(
            disc=disc, fuel_box=box,
            has_pitted=(_pit_flag(frame, disc, board_left)
                        if board_left else False)))
    return out if len(out) >= 2 else []


def pitted_count(frame) -> int:
    """How many cars are showing the pit columns.

    The cheapest useful thing here and it needs no digits at all: a car with
    the columns drawn has been to the pit lane, and one without has not.
    """
    return len(read(frame))
