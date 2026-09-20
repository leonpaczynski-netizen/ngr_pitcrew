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

**The country flag column and the pitch**, both from `board.flag_ladder`. This
module used to find them itself and no longer does: the same landmark was being
located twice, by two sets of thresholds, and `board`'s is the better of the two
- it finds the column by how many rows it yields rather than by how red it is,
which is what stops it returning the compound disc or the chroma fringe around
the names. One HUD change should mean one thing to fix.

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

import threading

import numpy as np

from pitcrew.diagnostics import log
from pitcrew.telemetry.board import flag_ladder

_log = log(__name__)

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
#
# **Re-measured on a full race, 15 Sep 2026, and kept.** Bathurst Rd 7
# (session 176), 13 cars, every row the live reader found at the live 2 s grab,
# each labelled with its driver from the NATIVE crop rather than from this
# roster (`tools/extract_board_identity_fixture.py`):
#
#                      pairs     min    0.1%    1%     5%    50%    95%    99%
#     different, 1 frame 22,687  0.641  0.687  0.753  0.789  0.883  0.936  0.957
#     same driver         7,800  0.020  0.030  0.050  0.079  0.233  0.674  0.814
#
# No pair of different drivers falls under anything up to 0.64; at 0.58 one
# same-driver pair in ten falls outside (the reader's band clips a glyph and
# the height-scaled bitmap moves), which splits a driver into a second cluster
# rather than merging two. The two tails overlap above 0.64, so no threshold
# is clean on both sides, and the Spa reasoning above about which way to err
# is reversed now that a merge is the expensive direction (see
# `test_board_identity_s176.py`). Handle "78" absorbing nine drivers that
# night was NOT this threshold: see `PitWall._neighbour`.
SAME_NAME_MAX_DIFF = 0.58

# **A sighting counts toward "is this a driver" at most once in this long.**
# Every sighting floor in the pit wall (`MIN_SIGHTINGS` = 20) was set when the
# board was grabbed every 2 s, so twenty meant forty seconds of being there.
# At a 0.5 s grab it means ten, and a misread cluster that held for ten
# seconds filed a stop as "Car #6" off TommyTbone's readings (critic, 19 Sep
# 2026, Sardegna Rd 9 replayed at 0.5 s). Counted on the clock, the floor
# keeps its meaning whatever the grab rate. `seen` still counts every frame,
# because it weights the exemplar and that should use every read.
SIGHTING_SPACING_S = 2.0

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


def is_own_row(board, y: int) -> bool:
    """Whether the ladder rung at `y` is the driver's own row.

    **Inside the plate, not within `ROW_MATCH_TOL` of its midpoint.** The
    plate is a row high, the rung is somewhere in it, and the midpoint is not
    where the ladder puts the rung: the driver's own white plate registers as
    flag colour over its whole height, so `board.flag_ladder` takes rungs out
    of its top and bottom EDGES - 365 and 396 on the frame traced in
    `board.CLIPPED_PLATE`, never one at its centre, 381. Asking whether a rung
    is within 8 px of the midpoint therefore answers **no** on a plate that
    was located perfectly.

    Measured 20 Sep 2026 over 292 frames of Bathurst (s204) and 182 of
    Sardegna (s188): this is the half of the clipped-plate fix that stops a
    regression. Repairing the box while this still asked about the midpoint
    took the own row from 82.9% to 58.9%, because a box grown to the plate's
    true extent moves its own midpoint AWAY from the rung the plate was found
    on. Together they give 60.3% -> 82.9% at Bathurst and 93.4% -> 98.9% at
    Sardegna, and two rows claiming to be ours on 0 frames of 474.

    **One function because the question is asked in two places** (rule 13):
    here and in `PitWall._own_driver`, which decides the same thing about the
    same board and must not decide it differently.
    """
    return board[1] <= y <= board[3]


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


def read(frame, board, ladder=None) -> list[BoardRow]:
    """Every leaderboard row this frame, with its name bitmap.

    Empty where the board could not be anchored. Ordered top to bottom, which is
    race order - but the ORDER is not the identity, and nothing downstream
    should treat a position as a key.

    `ladder` is `board.flag_ladder(frame)`. Pass it wherever the caller already
    has it: the grab is vsync-bound at about 16 ms and does not compose, so a
    live sampler must locate the board ONCE per frame and hand the result to
    every reader rather than letting each find it again.
    """
    if frame is None or getattr(frame, "ndim", 0) != 3 or board is None:
        return []
    own_y = (board[1] + board[3]) // 2
    if ladder is None:
        ladder = flag_ladder(frame)
    if not ladder:
        return []
    flag_x0, flag_x1, ys = ladder
    if not ys:
        return []
    # **Back off by the flag's own width before reading names.** `flag_ladder`
    # reports where the flag's SATURATED colour begins, and these are Union
    # Jacks: the white of the cross starts about a flag-width further left and
    # is bright, unsaturated and therefore indistinguishable from a name. Taken
    # at face value the bound sat inside the cross, the column vote landed on
    # the flag, and every name on all fourteen measured frames came back
    # unreadable while the rows themselves were found perfectly.
    right = max(0, flag_x0 - (flag_x1 - flag_x0 + 1))
    name_x = name_column(frame, board, ys, own_y, right)
    if name_x is None or name_x >= right:
        return []
    out = []
    for y in ys:
        # Inside the plate, not near its midpoint - see `is_own_row`.
        is_own = is_own_row(board, y)
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
        # **One lock, because this roster has two threads.** `see()` runs on
        # the sampler worker and appends to `_groups` and rewrites `_alias`
        # during a merge, while `named()`, `name_of()` and `label()` are
        # called from the Qt thread - `_resolve` walks `_alias` in a `while`
        # loop, and a walk over a dict being rewritten is a torn read at best.
        self._lock = threading.RLock()
        self._groups: list[dict] = []
        self._alias: dict[int, int] = {}
        # **Clusters that have been on the board in the same frame, and so are
        # two cars.** One car cannot hold two rows at once, which is the one
        # fact about identity a frame proves outright. `_merge_converged`
        # consults it, so two drivers who have been seen side by side are
        # never folded into one however alike their bitmaps grow.
        self._together: dict[int, set[int]] = {}
        # Rule 10: the accepts are counted as well as the refusals. `matched`
        # rows joined a cluster, `founded` started one, `contested` wanted a
        # cluster another row of the same frame was closer to, and `merged`
        # is one cluster folded into another by `_merge_converged`.
        #
        # **`merged` was the one number nobody had.** Bathurst, 20 Sep 2026:
        # seven cars became twenty-seven identities and 1,683 clusters were
        # founded, and the question "did the merge path run at all?" was
        # unanswerable from the artefacts - a merge was neither counted nor
        # logged, while the refusals were printed every two minutes. Rule 10
        # asks for the accepts, and this is the accept on the only path that
        # can undo a split.
        self.counts = {"matched": 0, "founded": 0, "contested": 0,
                       "merged": 0}
        for label, bits in (seed or {}).items():
            array = np.asarray(bits, dtype=bool)
            self._groups.append({"bits": array, "sum": array.astype(float),
                                 "seen": 1, "spaced": 1, "spaced_at": None,
                                 "label": label})

    def _resolve(self, index: int) -> int:
        # Under the lock: `see()` rewrites `_alias` on the sampler thread
        # while this walks it on the Qt one, and a chain rewritten mid-walk
        # does not resolve to anything in particular.
        with self._lock:
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
            if other in self._together.get(index, ()):
                # Seen on two rows of one frame: two cars, whatever the
                # bitmaps say now.
                continue
            if theirs["bits"].shape != mine["bits"].shape:
                continue
            apart_by = _distance(theirs["bits"], mine["bits"])
            if apart_by >= SAME_NAME_MAX_DIFF:
                continue
            if mine["seen"] >= theirs["seen"]:
                keep, drop = index, other
            else:
                keep, drop = other, index
            winner, loser = self._groups[keep], self._groups[drop]
            # Read before the fold, for the line below: afterwards the
            # winner's own count is gone into the total.
            kept_seen, lost_seen = winner["seen"], loser["seen"]
            kept_label, lost_label = winner["label"], loser["label"]
            winner["seen"] += loser["seen"]
            winner["spaced"] = winner.get("spaced", 0) + loser.get("spaced", 0)
            winner["sum"] = winner["sum"] + loser["sum"]
            winner["bits"] = (winner["sum"] / winner["seen"]) > 0.5
            winner["label"] = winner["label"] or loser["label"]
            self._alias[drop] = keep
            apart = self._together.pop(drop, set()) | self._together.get(keep, set())
            apart.discard(keep)
            apart.discard(drop)
            self._together[keep] = apart
            for other_id in apart:
                partners = self._together.setdefault(other_id, set())
                partners.discard(drop)
                partners.add(keep)
            self.counts["merged"] += 1
            # Rule 10, the accept said out loud: which cluster went into
            # which, how far apart the two exemplars had drifted, and what
            # each was carrying. A merge is the one event that can undo a
            # split, and it was invisible - so a race could not say whether
            # the path had run once or never.
            _log.info("roster: cluster %d (%s, %d sighting%s) folded into "
                      "cluster %d (%s, %d) - %.3f apart; now %s with %d, "
                      "%d merge%s this session",
                      drop, lost_label or "unnamed", lost_seen,
                      "" if lost_seen == 1 else "s",
                      keep, kept_label or "unnamed", kept_seen, apart_by,
                      winner["label"] or "unnamed", winner["seen"],
                      self.counts["merged"],
                      "" if self.counts["merged"] == 1 else "s")
            return keep
        return index

    def see(self, bits) -> int | None:
        """Fold one sighting in and return the driver id it belongs to.

        `None` for an unreadable bitmap: an unread name is not a new driver.
        One row on its own; a whole board is `see_frame`, which is what the
        pit wall calls.
        """
        return self.see_frame([bits])[0]

    def see_frame(self, bitmaps, *,
                  now: float | None = None) -> list[int | None]:
        """Every row of ONE frame, resolved together: a driver id per row.

        **Two rows of one frame are two cars**, so no id is handed to two of
        them. Rows are settled closest-first: a row whose nearest cluster was
        already taken by a closer row of the same frame falls to its next
        nearest untaken cluster under the threshold, and otherwise founds its
        own. The exemplar only moves for the row that won, never for the
        contested one - a reading the frame itself proves is somebody else
        must not pull a driver's bitmap toward that somebody.

        Measured on the Bathurst race of 14 Sep 2026 (session 176, 1,336
        frames at the live 2 s grab): two rows of one racing frame never
        measured closer than 0.574, so on a clean board this refuses nothing.
        It fires on the frames where the reader is NOT looking at a race
        board - the pre-race grid showed twelve identical "DR" plates - and
        that is exactly where one id would otherwise have been handed to
        twelve rows.
        """
        rows = [None if b is None else np.asarray(b, dtype=bool)
                for b in bitmaps]
        out: list[int | None] = [None] * len(rows)
        with self._lock:
            # **Nearest cluster, not the first one under the threshold.** An
            # earlier version took whichever group was created first, so a
            # bitmap 0.17 from one name and 0.05 from another joined the wrong
            # one purely by order of appearance.
            ranked: list[list[tuple[float, int]]] = []
            for bits in rows:
                if bits is None:
                    ranked.append([])
                    continue
                near = []
                for index, group in enumerate(self._groups):
                    if (index in self._alias
                            or group["bits"].shape != bits.shape):
                        continue
                    apart = _distance(group["bits"], bits)
                    if apart < SAME_NAME_MAX_DIFF:
                        near.append((apart, index))
                ranked.append(sorted(near))
            taken: set[int] = set()
            order = sorted((r for r in range(len(rows)) if rows[r] is not None),
                           key=lambda r: ranked[r][0][0] if ranked[r] else 2.0)
            contested = []
            for r in order:
                choice = next((i for _, i in ranked[r] if i not in taken), None)
                if ranked[r] and ranked[r][0][1] in taken:
                    contested.append((r, ranked[r][0][1], choice))
                if choice is None:
                    self._groups.append({"bits": rows[r],
                                         "sum": rows[r].astype(float),
                                         "seen": 1, "spaced": 1,
                                         "spaced_at": now, "label": None})
                    choice = len(self._groups) - 1
                    self.counts["founded"] += 1
                else:
                    group = self._groups[choice]
                    group["seen"] += 1
                    last = group.get("spaced_at")
                    if (now is None or last is None
                            or now - last >= SIGHTING_SPACING_S):
                        group["spaced"] = group.get("spaced", 0) + 1
                        group["spaced_at"] = now
                    group["sum"] = group["sum"] + rows[r]
                    group["bits"] = (group["sum"] / group["seen"]) > 0.5
                    self.counts["matched"] += 1
                taken.add(choice)
                out[r] = choice
            if contested:
                self.counts["contested"] += len(contested)
                # Rule 10: a refusal is said, with what it refused.
                _log.info("roster: %d row%s of one frame wanted a driver a "
                          "closer row already held - %s", len(contested),
                          "" if len(contested) == 1 else "s",
                          ", ".join(f"row {r + 1} wanted {want}, got "
                                    f"{'a new id' if got is None else got}"
                                    for r, want, got in contested))
            ids = [i for i in out if i is not None]
            for i in ids:
                self._together.setdefault(i, set()).update(
                    j for j in ids if j != i)
            for r, index in enumerate(out):
                if index is not None:
                    out[r] = self._merge_converged(index)
            return out

    def label(self, driver_id: int, text: str) -> None:
        """Name a cluster. Silently ignores an id that is not one.

        Bounds-checked like `name_of`, because a caller holding an id from
        before a merge is the ordinary case rather than a programming error.
        """
        with self._lock:
            if driver_id is None or not 0 <= driver_id < len(self._groups):
                return
            self._groups[self._resolve(driver_id)]["label"] = text

    def name_of(self, driver_id: int | None) -> str | None:
        with self._lock:
            if driver_id is None or not 0 <= driver_id < len(self._groups):
                return None
            return self._groups[self._resolve(driver_id)]["label"]

    def sightings(self, driver_id: int) -> int:
        with self._lock:
            if driver_id is None or not 0 <= driver_id < len(self._groups):
                return 0
            return self._groups[self._resolve(driver_id)]["seen"]

    def spaced_sightings(self, driver_id: int) -> int:
        """Sightings at most one per `SIGHTING_SPACING_S` - see there."""
        with self._lock:
            if driver_id is None or not 0 <= driver_id < len(self._groups):
                return 0
            return self._groups[self._resolve(driver_id)].get("spaced", 0)

    def drivers(self, min_sightings: int = 1, *,
                spaced: bool = False) -> list[int]:
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
        with self._lock:
            live = [i for i in range(len(self._groups)) if i not in self._alias]
            key = "spaced" if spaced else "seen"
            return sorted((i for i in live
                           if self._groups[i].get(key, 0) >= min_sightings),
                          key=lambda i: -self._groups[i]["seen"])

    def exemplar_of(self, driver_id: int):
        """One cluster's bitmap, named or not. `None` for an unknown id."""
        with self._lock:
            if driver_id is None or not 0 <= driver_id < len(self._groups):
                return None
            return self._groups[self._resolve(driver_id)]["bits"]

    def exemplars(self) -> dict[str, np.ndarray]:
        """Labelled clusters, for seeding the next race's roster."""
        with self._lock:
            return {self._groups[i]["label"]: self._groups[i]["bits"]
                    for i in self.drivers() if self._groups[i]["label"]}

    def __len__(self) -> int:
        with self._lock:
            return len([i for i in range(len(self._groups))
                        if i not in self._alias])
