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

### What this does not do yet

It does not read the fuel digits. It locates the box they are in. The pit flag
needs no reading at all — its presence IS the fact — so `has_pitted` is usable
today, and that alone tells the engineer who has stopped and who has not.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitcrew.telemetry.board import _runs

# A compound disc is a saturated red circle. These bounds are loose because the
# letter inside it is white and the disc is antialiased against whatever is
# behind the HUD.
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

# Discs are square to within antialiasing, and a column of them shares an x.
DISC_SQUARENESS = 0.65, 1.55
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


def _candidates(frame) -> list[tuple[int, int, int, int]]:
    red = ((frame[..., 0] > DISC_MIN)
           & (frame[..., 0] > frame[..., 1] * DISC_RATIO)
           & (frame[..., 0] > frame[..., 2] * DISC_RATIO))
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
