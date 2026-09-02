"""Who is on the leaderboard, and which row is which driver.

`board.py` finds the driver's own row. This finds everybody else's and puts a
name to each, so that a stop, a fuel figure and a compound stop being facts
about *row four* and become facts about *Rocky*.

### Why identity by name and not by row

A board row is not a car. GT7 reorders the board every time anybody passes
anybody, so a fuel figure read at row 2 on one lap and at row 2 on the next can
be two different drivers - and across a stop it usually IS, because a car in the
pit lane drops several places while it stands. Measured on the Spa replay of
1 Sep 2026, the top slot read 14 L then 12 L across 110 frames purely by cars
swapping under it. Anything that accumulates per rival - a burn rate, a stop
lap, a habit - accumulates nonsense unless the row is resolved to a driver.

### The three landmarks, none of them a fixed coordinate

**The country flag column.** Every car has one, pitted or not, and it is a
saturated rectangle repeated at one x - the same structure `pit_columns` uses
for the compound disc, and unlike the disc it is there from lap one. It gives a
candidate y for every row.

**The pitch, chained outward from the driver's own row.** Rows sit at a constant
pitch, except that GT7 inserts a gap readout immediately above and below the
driver's own row, so the first step out is larger than the rest. Measured at
1440p: pitch 40 px, first step 68. Both are read from the frame, never assumed,
and a candidate that does not continue the pitch is dropped - which is what
rejects the pit lane showing through the translucent HUD. On one Spa frame that
discarded six false rows and kept eight true ones, matching a hand count to a
pixel.

**The name column, by consensus across rows.** The name starts at the same x on
every row, so the rows vote and the majority wins. A single row can be wrong:
the driver's own row is a white plate with dark glyphs, and on one measured
frame it carried a two-pixel artifact eleven pixels left of its name that would
have shifted that row's crop on its own. Seven other rows outvoted it.

### The gap that makes a name separable at all

Between the position digit and the name is a gutter of **27-29 px**, measured
across eight rows. The widest gap *inside* a name - a space, as in "Magical
daddy" - is **9 px**. Merging ink across 12 px therefore joins a name to itself
and never to its position number, with three pixels of margin on one side and
fifteen on the other. Without that separation the bitmap would change every time
a driver changed position, which is exactly when identity matters most.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pitcrew.telemetry.board import _runs

# A flag is saturated colour; the HUD's greys and a name's white are not.
FLAG_SPREAD = 45
FLAG_CHANNEL_LEAD = 25
FLAG_CHANNEL_MIN = 70
FLAG_MIN_PIXELS = 6

# Ink merged across this many columns. Sits between the widest intra-name gap
# (a space, 9 px) and the position-digit gutter (27-29 px).
NAME_MERGE = 12

# Glyph thresholds. Bright text on everyone's translucent dark plate; dark text
# on the driver's own white one.
BRIGHT, DARK = 185, 120
# A column carries a glyph when this fraction of the row height is ink. Low
# enough for a thin stroke, high enough to ignore compression noise.
GLYPH_FRAC = 0.08
# Fewer ink pixels than this in a crop is not a name.
NAME_MIN_INK = 40
# **A name glyph is white or black, never coloured.** The board's right edge is
# not always in the same place relative to the country flag - measured at 241 px
# on one frame and 249 on another - so on some frames the flag falls inside the
# name search and, being the rightmost ink on the row, wins the column vote
# outright. It put `name_x` at 243 on a 249-wide board: a six-pixel crop, and
# every name on the frame unreadable. Saturation is what separates them, and it
# is the same test `board.py` uses to tell a plate from a flag.
NAME_MAX_SPREAD = 45

# Every name is normalised to this before comparison, so a crop one pixel wider
# is not a different driver.
#
# **Scaled by height and left-aligned, NOT stretched to fill.** Stretching makes
# "Beeni" and "Magical daddy" the same width, and on the Spa board those two
# came out 0.244 apart under a plain pixel-difference - inside the distance that
# is supposed to mean "same driver". **The length of a name is the most
# discriminating thing about it** and normalising it away throws out the best
# evidence on the frame.
NAME_SHAPE = (64, 16)

# **Two bitmaps closer than this are the same driver, measured as IoU.**
#
# The distance is one minus the intersection over the union of the ink, not the
# fraction of pixels that differ, and the difference between those two is the
# difference between this working and not. A plain pixel count is dominated by
# the blank canvas both names share, so two short names look alike because most
# of what they have in common is emptiness. Measured over sixteen hand-labelled
# rows across two Spa frames - eight same-driver pairs, 112 different-driver
# pairs:
#
#                      same driver          different drivers      gap
#     pixel difference max 0.113            min 0.204              0.091
#     IoU              max 0.392            min 0.774              0.383
#
# Four times the separation, and it is the reason the same eight names that
# collapsed into thirty-two clusters under a pixel count resolve cleanly here.
# 0.58 is the midpoint of the measured gap. The direction to err is wide: a
# split invents a driver and is invisible, a merge shows on the sheet the moment
# anybody looks at it.
SAME_NAME_MAX_DIFF = 0.58

# How far a row's y may sit from a pit disc's y and still be the same row.
ROW_MATCH_TOL = 8


def _distance(a, b) -> float:
    """One minus intersection-over-union of two name bitmaps.

    Blank canvas is shared by every name and says nothing about whose it is, so
    it is excluded from the denominator rather than counted as agreement.
    """
    union = int((a | b).sum())
    if union == 0:
        return 1.0
    return 1.0 - int((a & b).sum()) / union


@dataclass(frozen=True)
class BoardRow:
    """One car's row on the leaderboard.

    `name` is a normalised bitmap, not text - GT7's name font is proportional
    and mixed-case, and matching a bitmap is exact where reading it would be a
    guess. `None` means the name could not be read, which is a real state: the
    board reorders between frames and a row caught mid-reorder has two names
    drawn over each other.
    """
    y: int
    is_own: bool
    name: np.ndarray | None

    def matches(self, y: int) -> bool:
        """Whether a pit disc at this y belongs to this row."""
        return abs(self.y - y) <= ROW_MATCH_TOL


def _flag_mask(band):
    red, blue = band[..., 0], band[..., 2]
    saturated = (band.max(axis=2) - band.min(axis=2)) > FLAG_SPREAD
    coloured = (((blue > red + FLAG_CHANNEL_LEAD) & (blue > FLAG_CHANNEL_MIN))
                | ((red > blue + FLAG_CHANNEL_LEAD) & (red > FLAG_CHANNEL_MIN)))
    return saturated & coloured


def flag_span(frame, board) -> tuple[int, int] | None:
    """The x extent of the country flag column, or `None`.

    **The name has to stop where the flag starts, and the board's own right edge
    will not say where that is.** `own_row` returned 241 on one measured frame
    and 249 on another with the flag beginning at 242 in both, so on the second
    the flag's leading seven pixels sat inside the name search. That matters
    more than it sounds: these are Union Jacks, and the white of the cross
    passes any test for "bright and not coloured" that a white name passes.
    Being the rightmost ink on every row, it won the column vote outright and
    put the name band at 243 on a 249-wide board - a six-pixel crop, and every
    name on the frame unreadable.

    **The column is chosen by whether it looks like a ruler, not by how red it
    is.** Two cheaper rules were measured and both failed: the densest run finds
    the compound disc, which is a solid circle where a flag is half white, and
    the leftmost run finds the chroma fringing around the names themselves - a
    seven-pixel smear at x 198 that took the row count from eight to zero. A
    flag column carries one mark per row at the board's pitch and nothing else
    on the screen does, so each candidate is scored by how many rows it yields
    and the best one wins. Ties go to the leftmost, which is the flag rather
    than the disc.
    """
    height = board[3] - board[1] + 1
    own_y = (board[1] + board[3]) // 2
    left = max(0, board[2] - height)
    band = frame[:, left:board[2] + 3 * height]
    if band.size == 0:
        return None
    per_column = _flag_mask(band).sum(axis=0)
    if not per_column.any():
        return None
    runs = [r for r in _runs(np.where(per_column > FLAG_MIN_PIXELS)[0], 3)
            if len(r) >= 4]
    best, best_rows = None, 0
    for run in runs:
        span = (left + int(run[0]), left + int(run[-1]))
        found = len(chain(flag_rows(frame, board, span), own_y, height))
        if found > best_rows:
            best, best_rows = span, found
    return best


def flag_rows(frame, board, span=None) -> list[int]:
    """Candidate row centres, from the country flag column.

    Candidates only - scenery behind the translucent HUD is saturated too.
    `chain` is what separates the board from the pit lane behind it.
    """
    if span is None:
        span = flag_span(frame, board)
    if span is None:
        return []
    band = frame[:, span[0]:span[1] + 1]
    if band.size == 0:
        return []
    per_row = _flag_mask(band).sum(axis=1)
    return [int((run[0] + run[-1]) / 2)
            for run in _runs(np.where(per_row > FLAG_MIN_PIXELS)[0], 3)
            if len(run) >= 6]


def chain(candidates: list[int], own_y: int, height: int,
          tol: int = 5) -> list[int]:
    """Keep the candidates that continue a constant pitch from the own row.

    **This is the whole guard, and it is the argument `_on_a_pitch` makes in
    `pit_columns`.** A leaderboard is a ruler; a pit lane is not. Red and blue
    scenery lands at arbitrary spacings, so it breaks the chain, and everything
    beyond a break is dropped - deliberately, because a row found past a gap
    cannot be numbered.

    The first step out is the larger one: GT7 draws a gap readout immediately
    above and below the driver's own row. Every step after it must match the
    pitch, and the pitch is taken from the frame rather than from a constant.
    """
    if not candidates:
        return []
    near = min(candidates, key=lambda y: abs(y - own_y))
    kept = [near]
    for side in (sorted([y for y in candidates if y < near - tol],
                        reverse=True),
                 sorted([y for y in candidates if y > near + tol])):
        previous, pitch = near, None
        for index, y in enumerate(side):
            step = abs(y - previous)
            if index == 0:
                if step > 2.5 * height:
                    break            # not a neighbouring row at all
            elif pitch is None:
                if step > 1.5 * height:
                    break
                pitch = step
            elif abs(step - pitch) > tol:
                break
            kept.append(y)
            previous = y
    return sorted(kept)


def _half(board) -> int:
    return max(6, (board[3] - board[1]) // 3)


def _ink(strip, is_own):
    """Name glyphs in a strip: bright or dark, and never coloured."""
    lum = strip.mean(axis=2)
    grey = (strip.max(axis=2) - strip.min(axis=2)) < NAME_MAX_SPREAD
    return grey & ((lum < DARK) if is_own else (lum > BRIGHT))


def _merged(on) -> list[tuple[int, int]]:
    groups, start = [], None
    for index, value in enumerate(list(on) + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            groups.append((start, index - 1))
            start = None
    out: list[tuple[int, int]] = []
    for group in groups:
        if out and group[0] - out[-1][1] - 1 <= NAME_MERGE:
            out[-1] = (out[-1][0], group[1])
        else:
            out.append(group)
    return out


def name_column(frame, board, ys: list[int], own_y: int,
                right: int | None = None) -> int | None:
    """Where names start, by majority vote of the rows.

    Every row agrees, so a row that disagrees is wrong - and one always might
    be, because the own row's white plate picks up artifacts a dark plate does
    not.
    """
    half = _half(board)
    votes: dict[int, int] = {}
    for y in ys:
        strip = frame[max(0, y - half):y + half,
                      0:(board[2] if right is None else right)]
        if strip.size == 0:
            continue
        is_own = abs(y - own_y) <= ROW_MATCH_TOL
        ink = _ink(strip, is_own)
        groups = _merged((ink.sum(axis=0) / strip.shape[0]) > GLYPH_FRAC)
        if groups:
            votes[groups[-1][0]] = votes.get(groups[-1][0], 0) + 1
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0]


def name_bitmap(frame, board, y: int, name_x: int, is_own: bool,
                right: int | None = None):
    """One row's name, cropped to its ink and normalised, or `None`."""
    from PIL import Image

    half = _half(board)
    strip = frame[max(0, y - half):y + half,
                  name_x:(board[2] if right is None else right)]
    if strip.size == 0:
        return None
    ink = _ink(strip, is_own)
    if ink.sum() < NAME_MIN_INK:
        return None
    # **Crop to the name's own ink group, not to whatever is leftmost.** The
    # band's left edge is a consensus across rows, so an individual row can
    # carry a stray blob a few pixels inside it - the white own-row plate
    # reliably does. Cropping to the outermost ink then shifts the whole name
    # right and pads its width, and the same driver clusters two and three
    # times over: measured on 30 clean Spa frames, "Beeni" came back as three
    # separate clusters of 12, 9 and 4 sightings, and Boxhead and A.Maidment as
    # two each. A name is one group once spaces are merged, and a stray is a
    # narrow group of its own, so the widest group is the name.
    groups = _merged(ink.any(axis=0))
    if not groups:
        return None
    x_from, x_to = max(groups, key=lambda g: g[1] - g[0])
    if x_to - x_from < 4:
        return None
    body = ink[:, x_from:x_to + 1]
    rows_on = np.where(body.any(axis=1))[0]
    if len(rows_on) < 4 or body.sum() < NAME_MIN_INK:
        return None
    crop = body[rows_on.min():rows_on.max() + 1]
    width, height = NAME_SHAPE
    scale = height / crop.shape[0]
    wide = max(1, min(width, int(round(crop.shape[1] * scale))))
    scaled = Image.fromarray((crop * 255).astype("uint8")).resize((wide, height))
    canvas = np.zeros((height, width), dtype=bool)
    canvas[:, :wide] = np.asarray(scaled) > 127
    return canvas


def read(frame, board) -> list[BoardRow]:
    """Every leaderboard row this frame, with its name bitmap.

    Empty where the board could not be anchored. Ordered top to bottom, which is
    race order - but the ORDER is not the identity, and nothing downstream
    should treat a position as a key.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3 or board is None:
        return []
    own_y = (board[1] + board[3]) // 2
    height = board[3] - board[1] + 1
    span = flag_span(frame, board)
    if span is None:
        return []
    ys = chain(flag_rows(frame, board, span), own_y, height)
    if not ys:
        return []
    right = span[0]
    name_x = name_column(frame, board, ys, own_y, right)
    if name_x is None or name_x >= right:
        return []
    out = []
    for y in ys:
        is_own = abs(y - own_y) <= ROW_MATCH_TOL
        out.append(BoardRow(
            y=y, is_own=is_own,
            name=name_bitmap(frame, board, y, name_x, is_own, right)))
    return out


class Roster:
    """Stable driver identities across a session, and across races.

    A cluster is a driver. It is founded by the first bitmap that matches
    nothing, and every later sighting is compared against the cluster's running
    average rather than against its first member - a cluster founded on an
    atypical crop, caught mid-reorder or half behind a pit crew, otherwise
    compares everything against its own worst evidence for the rest of the race.

    `label` is how a cluster gets a human name, and giving it is the driver's
    job: reading a proportional mixed-case font is a guess, and this app does
    not guess at whose car it is looking at. Seeding from a previous race's
    exemplars is how that labelling survives into the next race.
    """

    def __init__(self, seed: dict[str, np.ndarray] | None = None):
        self._groups: list[dict] = []
        self._alias: dict[int, int] = {}
        for label, bits in (seed or {}).items():
            array = np.asarray(bits, dtype=bool)
            self._groups.append({"bits": array, "sum": array.astype(float),
                                 "seen": 1, "label": label})

    def _resolve(self, index: int) -> int:
        while index in self._alias:
            index = self._alias[index]
        return index

    def _merge_converged(self, index: int) -> int:
        """Fold a cluster into another it has drifted into.

        **Founding order, not similarity, is what splits a driver in two.** A
        cluster is created whenever the incoming bitmap is too far from every
        exemplar *at that moment*; both then move as their averages fill in, and
        two clusters for one driver can end up closer than the threshold that
        was supposed to prevent them existing. Measured over 30 clean Spa
        frames, CruisingChaos came back twice, 17 sightings and 9, with the two
        exemplars **0.406** apart - while the nearest genuinely different pair
        on the same board sat at **0.738**. Nothing distinguished them except
        when they were founded.

        Two clusters a human has given DIFFERENT names are never merged: a
        person saying they are two drivers outranks a bitmap saying they look
        alike.
        """
        index = self._resolve(index)
        mine = self._groups[index]
        for other in range(len(self._groups)):
            if other == index or other in self._alias:
                continue
            theirs = self._groups[other]
            if (mine["label"] and theirs["label"]
                    and mine["label"] != theirs["label"]):
                continue
            if theirs["bits"].shape != mine["bits"].shape:
                continue
            if _distance(theirs["bits"], mine["bits"]) >= SAME_NAME_MAX_DIFF:
                continue
            if mine["seen"] >= theirs["seen"]:
                keep, drop = index, other
            else:
                keep, drop = other, index
            winner, loser = self._groups[keep], self._groups[drop]
            winner["seen"] += loser["seen"]
            winner["sum"] = winner["sum"] + loser["sum"]
            winner["bits"] = (winner["sum"] / winner["seen"]) > 0.5
            winner["label"] = winner["label"] or loser["label"]
            self._alias[drop] = keep
            return keep
        return index

    def see(self, bits) -> int | None:
        """Fold one sighting in and return the driver id it belongs to.

        `None` for an unreadable bitmap: an unread name is not a new driver.
        """
        if bits is None:
            return None
        bits = np.asarray(bits, dtype=bool)
        # **Nearest cluster, not the first one under the threshold.** An earlier
        # version took whichever group was created first, so a bitmap 0.17 from
        # one name and 0.05 from another joined the wrong one purely by order of
        # appearance.
        best, closest = None, None
        for index, group in enumerate(self._groups):
            if index in self._alias or group["bits"].shape != bits.shape:
                continue
            apart = _distance(group["bits"], bits)
            if closest is None or apart < closest:
                best, closest = index, apart
        if best is not None and closest < SAME_NAME_MAX_DIFF:
            group = self._groups[best]
            group["seen"] += 1
            group["sum"] = group["sum"] + bits
            group["bits"] = (group["sum"] / group["seen"]) > 0.5
            return self._merge_converged(best)
        self._groups.append({"bits": bits, "sum": bits.astype(float),
                             "seen": 1, "label": None})
        return len(self._groups) - 1

    def label(self, driver_id: int, text: str) -> None:
        self._groups[self._resolve(driver_id)]["label"] = text

    def name_of(self, driver_id: int | None) -> str | None:
        if driver_id is None or not 0 <= driver_id < len(self._groups):
            return None
        return self._groups[self._resolve(driver_id)]["label"]

    def sightings(self, driver_id: int) -> int:
        return self._groups[self._resolve(driver_id)]["seen"]

    def drivers(self, min_sightings: int = 1) -> list[int]:
        """The ids that are actually drivers, commonest first.

        **A driver appears on nearly every frame; a bad read appears once.** The
        board is drawn over the racing scene, so a marshal walking across the
        HUD, a frame caught mid-reorder with two names rendered over each other,
        or a row half behind a pit crew each produce a bitmap that resembles
        nothing and founds a cluster of its own. Measured on the Spa replay
        those tails were forty-odd clusters of a single sighting, against eight
        drivers seen 17 to 26 times in 30 frames. Sustained sightings is the
        same run-length argument the board locator makes about bright pixels,
        and it is the only thing that separates the two populations.
        """
        live = [i for i in range(len(self._groups)) if i not in self._alias]
        return sorted((i for i in live
                       if self._groups[i]["seen"] >= min_sightings),
                      key=lambda i: -self._groups[i]["seen"])

    def exemplars(self) -> dict[str, np.ndarray]:
        """Labelled clusters, for seeding the next race's roster."""
        return {self._groups[i]["label"]: self._groups[i]["bits"]
                for i in self.drivers() if self._groups[i]["label"]}

    def __len__(self) -> int:
        return len([i for i in range(len(self._groups))
                    if i not in self._alias])
