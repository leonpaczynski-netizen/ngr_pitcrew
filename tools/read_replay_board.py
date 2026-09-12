"""Name the cars either side of him, off the replay's leaderboard.

    python tools/read_replay_board.py --session 88 --video "<path>" \
        --every 4 --offset 8.10                    # find the names
    # ...write the names into the roster it produced, then:
    python tools/read_replay_board.py --session 88 --video "<path>" \
        --every 4 --offset 8.10 --apply

**`traffic.rival_position` says which car; it does not say WHICH car.** A
position is not an identity - the car that was P6 on lap 14 can be P8 by lap
18 - so "the same car sat behind him for four laps" is not answerable from the
position column alone. The name is, and it is on the leaderboard.

### No OCR, and none needed

Nothing on this machine has an OCR engine and none is wanted. GT7 renders
these names in one font at one size, so the same name is the same bitmap every
time: the strips are cropped to their ink, normalised, and clustered by
Hamming distance. That is exact where OCR would be probabilistic, and the
operator labels each cluster once by looking at it.

**And what he was given to look at was the normalised exemplar**, 64x16, which
is the clustering's working copy and not a picture of anything: the name column
is 142x24 on the canvas, so the strokes that tell `Seeni` from `Beeni` are
squashed out of it before it is ever written to disk.
Each cluster now also writes `name-<session>-<n>-raw.png` - its three clearest
sightings at native resolution - and that is the one to open. Labelling from
the exemplar is guessing at a driver's name, which is the one thing this tool
refuses to do at every other step.

### Finding the rows, on a panel you can see through

The leaderboard is translucent and the scenery behind it moves, so thresholding
for rows finds sky as often as it finds a row - measured, on 3 frames of 7.
Two anchors survive that:

* **the flags.** One per driver row, at a fixed x, a saturated blue nothing
  behind the panel reproduces. They give the row grid at a 40 px pitch, and
  the 67-72 px steps are where a gap row sits - a row that carries a time and
  no flag.

  **A flag is not a place in the running order, though, and that cost a
  driver's name.** The fastest-lap banner at the foot of the board carries one
  too, so a flag row was read as the car behind the last-placed driver - and
  the FL banner names whoever holds the fastest lap, which on the Sardegna
  rehearsal was HIS OWN. 27 sightings of himself as his own rival, in a
  three-car race with no fourth car to find.

  **And it is not separable by spacing**, which is the second thing that cost
  time. On that three-car board the banner sits 259-291 px below the last row,
  because nothing is between them; on a full board it sits **60 px** down,
  inside the range a gap readout already occupies. The rule that holds in both
  is position: the banner is the last thing on the board wearing a flag, and
  nothing with a flag is drawn below it, so the bottom-most flag is never read
  as the car behind him. `board_rows` still drops far-separated panels, which
  is what catches scenery ABOVE the board - the other direction, where the
  bottom-most rule cannot help.
* **his own row is white-backed.** Measured across 36 frames: 171-203 mean
  luminance against 75-147 for the brightest other row, which is a separation
  no bleed-through has closed.

His row is therefore unambiguous, and the flag row above and below it are the
cars at his position minus and plus one. **Nothing here reads a digit.** The
position comes from `laps.position`, which is in the packet and already in the
archive; this only has to say who is in the next row up and the next row down.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                              # noqa: E402

CANVAS = (1920, 1080)
# The flag column, and the band of the board worth searching.
FLAG_X = (245, 290)
BOARD_Y = (150, 700)
NAME_X = (100, 242)
# A flag is this tall. Anything else in that column is not one.
FLAG_MIN_H, FLAG_MIN_FRAC = 8, 0.30
FLAG_MAX_H = 34
# **How far apart two rows may be and still be the same board.** The board is
# the run of rows containing his own, and anything further than one step from
# it is another panel - scenery above it, most often, which `flag_rows` does
# fire on.
#
# Measured over 240 frames of the Sardegna rehearsal:
#
#     step between rows on the board        37 - 72 px  (n=122)
#
# **This is NOT what excludes the fastest-lap banner, though it was written to
# be.** On that three-car board the banner sat 259-291 px down and the split
# looked clean; on a full board it sits 60 px below the last driver, inside the
# gap-readout range, and no threshold separates them. `read_frame` refuses the
# bottom-most flag instead. Left here, widened, for the far-separated case.
#
# **150, not 120, because 120 can cut the board through HIS row.** GT7 draws a
# gap readout above AND below the driver's own row, each pitch plus a constant
# - 40 and 68 measured (`telemetry/board.py`). If his own flag is missed, and
# his is the likeliest to be missed because his row is washed toward white, the
# step from the row above him to the row below is 68 + 68 = 136. At 120 the
# board splits at exactly his row and a row at the split boundary is read as a
# neighbour.
MAX_ROW_STEP = 150
# How far his white-backed row must out-shine every other flag in the picture,
# and how bright it must be in absolute terms. Measured 171-203 for his row
# against 75-147 for the brightest other; the banner sits at 15-27.
OWN_ROW_MARGIN = 20
OWN_ROW_MIN_LUM = 150
# **A name is strokes; a filled rectangle is not a name.** When the row grid
# picks up scenery his white-backed row can end up beside the one thought to be
# his, and reading a WHITE row with the rival polarity makes the background the
# ink - a solid block, which then clusters with every other solid block and
# arrives as a driver nobody can identify. Same 240 frames:
#
#     a rival's name                    fill 0.126 - 0.422
#     his own row read as a rival       fill 0.906 - 0.918
#     scenery in the flag column        fill 0.018, and 0.595 - 0.814
#
# **0.50, not 0.60.** The ceiling was first set at 0.60 against a scenery floor
# measured at 0.595 in the same sweep - five thousandths from admitting the
# exact thing the constant was added to reject, and on the wrong side of the
# only gap that matters. 0.50 sits in the middle of the 0.422-0.595 gap, which
# is the widest margin available in both directions at once.
#
# The floor stays low because a name arriving with one stray bright pixel at
# the edge of the strip has its bounding box inflated to the full 142x24 and
# its fill driven toward 0.01.
#
# The ceiling was first put on the wrong side of that gap by reasoning this
# file withdraws forty lines further down - *"a split invents a driver and is
# invisible"*, so err wide. That held while the operator could not read the
# crop. It cannot be used to justify a bound here and be withdrawn there.
NAME_FILL = (0.05, 0.50)
# Half-height of the strip a name is read from, about the flag's centre.
NAME_HALF_H = 12
# Fewer ink pixels than this is not a name.
NAME_MIN_INK = 40
# Every name is normalised to this before being compared, so a crop a pixel
# wider does not read as a different driver.
NAME_SHAPE = (64, 16)
# **Two bitmaps closer than this are the same name.** Raised twice, both times
# because the same driver split into two clusters - at 0.12 on the Fuji race,
# and again at 0.18 on Spa session 112, where PUNISHED came back as cluster 0
# with 591 sightings and cluster 9 with one.
#
# Measured across that roster's ten clusters, the two populations do not
# overlap and there is room between them:
#
#     same driver (PUNISHED to PUNISHED)      0.205
#     nearest DIFFERENT pair of the other 44  0.289
#
# 0.25 sits in that gap with about four hundredths of margin either side.
#
# **12 Sep: that margin is not there any more, and the reason to want it has
# gone too.** Sardegna 159 is a three-car race, and on its final exemplars:
#
#     same driver (J.Jonas, clusters 0 and 2)  0.244
#     different drivers (J.Jonas / K.Graebs)   0.283
#
# 0.039 apart in total, with the threshold 0.006 above the same-driver pair -
# which still split, because the comparison is made against a running average
# that had not yet converged when the second cluster was founded. The
# populations very nearly touch, so no threshold separates them reliably and
# raising this one buys a merge of two real drivers.
#
# **It is left where it is, and the old reasoning for widening it is
# withdrawn.** That reasoning - *"a split invents a driver and is
# invisible"* - was true when the operator was handed the unreadable 64x16
# exemplar. They are now handed the native crop, where `J.Jonas` twice is
# plain, gets the same label twice, and costs nothing. A MERGE is the
# expensive direction now: it puts one driver's name on another's car with
# nothing left to notice it by.
SAME_NAME_MAX_DIFF = 0.25
# **What to write against a cluster nobody can read.** The board reorders
# between frames and a sample caught mid-reorder has two names rendered over
# each other. Marking it explicitly leaves those contacts unnamed and lets the
# rest through; leaving it blank blocks everything, and guessing at it puts a
# driver's name on a car that was never there.
UNREADABLE = "-"
# How many of a cluster's own sightings to put in front of the operator, and
# how far to blow them up. Nearest-neighbour at 6x: no interpolation, so no
# stroke appears that the board did not draw.
RAW_SAMPLES = 3
RAW_SCALE = 6
# How many of the most typical sightings the three are then spread across. Wide
# enough that the three are not neighbours in time, short enough that a badly
# cut crop does not reach the sheet.
RAW_SHORTLIST = 24


def _legible(crops, path) -> None:
    """Stack a cluster's clearest native crops into one readable PNG."""
    from PIL import Image
    import numpy as np
    crops = [c for c in crops if c is not None and c.size]
    if not crops:
        return
    width = max(c.shape[1] for c in crops)
    rows = []
    for crop in crops:
        pad = np.zeros((crop.shape[0], width), dtype=bool)
        pad[:, :crop.shape[1]] = crop
        rows.append(pad)
        rows.append(np.zeros((2, width), dtype=bool))
    stack = np.vstack(rows[:-1])
    # Dark on light. The board draws these bright on a translucent panel, but
    # ink on paper is what an eye reads best at this size.
    image = Image.fromarray(((~stack) * 255).astype("uint8"))
    image.resize((width * RAW_SCALE, stack.shape[0] * RAW_SCALE),
                 Image.NEAREST).save(path)


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                            # noqa: BLE001
        return "ffmpeg"


def frame_at(video: Path, seconds: float, out: Path) -> bool:
    result = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1",
         "-y", str(out)], capture_output=True)
    return result.returncode == 0 and out.exists()


def flag_rows(pixels) -> list[int]:
    """The y of every driver row, found by its flag."""
    strip = pixels[BOARD_Y[0]:BOARD_Y[1], FLAG_X[0]:FLAG_X[1]].astype(int)
    r, g, b = strip[:, :, 0], strip[:, :, 1], strip[:, :, 2]
    blue = (b > 90) & (b - r > 45) & (b - g > 30)
    share = blue.mean(axis=1)
    rows, start = [], None
    for i, value in enumerate(share):
        if value > FLAG_MIN_FRAC and start is None:
            start = i
        elif value <= FLAG_MIN_FRAC and start is not None:
            if FLAG_MIN_H <= i - start <= FLAG_MAX_H:
                rows.append((start + i) // 2 + BOARD_Y[0])
            start = None
    return rows


def _brightness(pixels, rows: list[int]) -> list[float]:
    return [pixels[y - 13:y + 13, NAME_X[0]:NAME_X[1]].mean() for y in rows]


def board_rows(pixels, rows: list[int]) -> list[int]:
    """Of everything wearing a flag, the rows that are the running order.

    The board is a contiguous run at its own pitch, anchored on his own
    white-backed row. Two things are dropped: a panel further than one step
    from that run - **scenery above the board**, which `flag_rows` does fire
    on, measured at y=163 with his row at 424 - and any frame where no row
    out-shines the rest, because then his own row cannot be told apart.

    **Not the fastest-lap banner**, which was what this was first written for
    and which it cannot do: on a full board the banner sits sixty pixels below
    the last driver, inside the gap-readout range, so no spacing separates
    them. `read_frame` refuses the bottom-most flag instead.
    """
    if not rows:
        return []
    # **The anchor is chosen BEFORE the pruning, and that ordering is the
    # whole guard.** Picking the run first and asking which row is his second
    # made `own_row`'s margin strictly easier to pass: pruning can only remove
    # rows, so the brightest of what survives beats a weaker field than the
    # brightest of everything did. On rows at 197/265/304/592 lit 200/90/95/190
    # the margin over ALL of them refuses the frame, and the margin over a
    # pruned pair does not. So his row must out-shine every flag in the
    # picture, not merely the ones sharing its panel.
    lit = _brightness(pixels, rows)
    best = max(range(len(rows)), key=lambda i: lit[i])
    others = sorted(lit)[:-1]
    if others and lit[best] - max(others) < OWN_ROW_MARGIN:
        return []
    # ...and it must actually look like the white-backed row, not merely be
    # the brightest thing present. A dark banner alone in a dark frame wins a
    # contest it should not have entered.
    if lit[best] < OWN_ROW_MIN_LUM:
        return []
    anchor = rows[best]
    runs, run = [], [rows[0]]
    for previous, y in zip(rows, rows[1:]):
        if y - previous <= MAX_ROW_STEP:
            run.append(y)
        else:
            runs.append(run)
            run = [y]
    runs.append(run)
    for candidate in runs:
        if anchor in candidate:
            # **A lone row is not a running order.** A run of one means his
            # row was found with no neighbour inside a board's pitch of it -
            # there is nobody to name, and saying so here means the frame is
            # COUNTED as one his row could not be told apart rather than
            # passing silently on index arithmetic that falls off both ends.
            return candidate if len(candidate) > 1 else []
    raise AssertionError("the anchor is one of the rows the runs partition")


def own_row(pixels, rows: list[int]) -> int | None:
    """Which of those rows is his. **The white background, not the position.**"""
    if not rows:
        return None
    brightness = _brightness(pixels, rows)
    best = max(range(len(rows)), key=lambda i: brightness[i])
    # A row that is not clearly brighter than the rest is not his: the panel
    # is translucent and a white wall behind it can lift any row. `board_rows`
    # has already applied this over every flag in the picture, which is the
    # stronger test; this stays for callers that have not been through it.
    others = sorted(brightness)[:-1]
    if others and brightness[best] - max(others) < OWN_ROW_MARGIN:
        return None
    return best


def name_bitmap(pixels, y: int, own: bool, tally=None):
    """One row's name: the normalised bits, and the crop they came from.

    **Two things, because they are for two different readers.** The 64x16
    normalisation exists so that a crop a pixel wider does not read as a
    different driver - it is for the clustering, which compares bitmaps and
    never looks at them. The operator DOES look, and at 16 px tall there is
    nothing left to look at: the name column is 142x24 on the canvas, and
    squashing it to 64x16 destroys exactly the strokes that tell one name
    from another. Labelling a roster off the normalised exemplar is guessing
    at a driver's name, so the native crop is carried alongside it.

    **`tally` counts the refusals**, and it is not decoration. CLAUDE.md 4.10
    is the tyre-gauge ratchet: a band set a few thousandths wrong refuses
    everything for a whole session and is invisible while it does, because
    only the accepts were ever reported. A run that rejected four hundred
    strips as "too dense" has a broken threshold, not a quiet race, and the
    only way to see that is to print it.
    """
    from PIL import Image
    import numpy as np

    def refuse(reason):
        if tally is not None:
            tally[reason] += 1
        return None

    strip = pixels[y - NAME_HALF_H:y + NAME_HALF_H,
                   NAME_X[0]:NAME_X[1]].astype(int)
    if strip.size == 0:
        return refuse("off the canvas")
    lum = strip.mean(axis=2)
    # Dark glyphs on his white row, bright glyphs on everyone else's.
    ink = lum < 120 if own else lum > 185
    ys, xs = np.where(ink)
    if len(xs) < NAME_MIN_INK:
        return refuse("too little ink")
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    # Strokes, not a filled rectangle - see `NAME_FILL`. A row that fails this
    # is scenery, or his own white row read with the rival polarity; either
    # way it is not a name and must not become a cluster.
    fill = crop.mean()
    if fill < NAME_FILL[0]:
        return refuse("too sparse to be a name")
    if fill > NAME_FILL[1]:
        return refuse("too dense to be a name")
    scaled = Image.fromarray((crop * 255).astype("uint8")).resize(NAME_SHAPE)
    return np.asarray(scaled) > 127, crop


def read_frame(pixels, tally=None):
    """The cars either side of him on one frame: `(side, y, bits, crop)`.

    `None` when his own row could not be told apart, which is a different
    answer from "nobody was beside him" and is counted separately.

    **This exists so the wiring can be tested.** Every guard in this file -
    dropping the fastest-lap banner, refusing a frame whose brightest flag is
    not a white-backed row, rejecting a filled rectangle that is not a name -
    is worthless if the reading loop does not call it, and while that loop
    lived inside `main` nothing could check that it did. Reverting the one
    line that prunes the rows passed the entire suite.
    """
    flags = flag_rows(pixels)
    rows = board_rows(pixels, flags)
    index = own_row(pixels, rows)
    if index is None:
        return None
    # **The bottom-most flag in the picture is never the car behind him**, and
    # this is the guard that actually holds, because the step rule does not.
    #
    # `MAX_ROW_STEP` was measured on a THREE-CAR board, where the banner sits
    # 259-291 px below the last row because there is nothing between them. On
    # a full board it sits **60 px** below the last driver - inside the 66-67
    # px a gap readout already occupies - so no spacing separates them and the
    # banner walks straight through a step rule at any threshold. Measured on
    # Daytona session 142: rows at 196/235/276/316/356/423/489/529 and the
    # banner at 589.
    #
    # What does hold in both layouts is position: the fastest-lap banner is
    # the last thing on the board wearing a flag, and nothing with a flag is
    # ever drawn below it. Refusing that one row costs the genuinely last car
    # as a `behind` contact on the early laps before anyone has set a fastest
    # lap and the banner is absent - a contact dropped, never a contact
    # invented, which is the only direction this defect may be wrong in.
    bottom = flags[-1] if flags else None
    found = []
    for offset, side in ((-1, "ahead"), (1, "behind")):
        j = index + offset
        if not 0 <= j < len(rows):
            continue
        y = rows[j]
        if side == "behind" and y == bottom:
            if tally is not None:
                tally["the bottom flag, where the FL banner sits"] += 1
            continue
        read = name_bitmap(pixels, y, own=False, tally=tally)
        if read is not None:
            found.append((side, y, read[0], read[1]))
    return found


def cluster(bitmaps: list) -> list[dict]:
    """Group identical names. Exact, because the font never changes."""
    groups: list[dict] = []
    for key, bits in bitmaps:
        # **Nearest cluster, not the first one under the threshold.** The old
        # loop took whichever group happened to be created first, so a bitmap
        # 0.17 from one name and 0.05 from another joined the wrong one purely
        # by order of appearance. With the threshold now wider that would
        # matter more, not less.
        best, closest = None, None
        for group in groups:
            apart = (group["bits"] != bits).mean()
            if closest is None or apart < closest:
                best, closest = group, apart
        if best is not None and closest < SAME_NAME_MAX_DIFF:
            best["seen"].append(key)
            # **And the exemplar is the running average, not the first sample
            # seen.** A cluster founded on an atypical crop - caught mid-
            # reorder, or partly behind a pit crew - compared everything
            # against its worst member for the rest of the race. Averaging
            # makes the exemplar more typical as evidence arrives rather than
            # less.
            best["sum"] = best["sum"] + bits
            best["bits"] = (best["sum"] / len(best["seen"])) > 0.5
        else:
            groups.append({"bits": bits, "sum": bits.astype(float),
                           "seen": [key]})
    # **A pass over the finished exemplars, because one streaming pass is
    # order-dependent and that is what actually splits a driver in two.**
    # Each bitmap is compared against an average that has not converged yet,
    # so a cluster founded early on an atypical crop never gets re-examined -
    # nothing re-compares two groups once both exist. Sardegna 159 ended with
    # `J.Jonas` as two clusters whose FINAL exemplars are 0.244 apart, inside
    # this same threshold: by the end the evidence said one driver and the
    # answer still said two. Repeating to a fixed point makes the result
    # independent of the order the frames arrived in.
    merged = True
    while merged and len(groups) > 1:
        merged = False
        for i in range(len(groups)):
            for j in range(i + 1, len(groups)):
                if (groups[i]["bits"] != groups[j]["bits"]).mean() \
                        < SAME_NAME_MAX_DIFF:
                    groups[i]["seen"].extend(groups[j]["seen"])
                    groups[i]["sum"] = groups[i]["sum"] + groups[j]["sum"]
                    groups[i]["bits"] = (
                        groups[i]["sum"] / len(groups[i]["seen"])) > 0.5
                    del groups[j]
                    merged = True
                    break
            if merged:
                break
    groups.sort(key=lambda group: -len(group["seen"]))
    return groups


def crossings(store: Store, session_id: int, offset_s: float):
    laps = store.list_laps(session_id)
    if not laps:
        raise SystemExit(f"session {session_id} has no laps")
    first = dt.datetime.fromisoformat(laps[0]["recorded_at"])
    start = first - dt.timedelta(milliseconds=laps[0]["lap_time_ms"])
    return [((dt.datetime.fromisoformat(row["recorded_at"]) - start
              ).total_seconds() + offset_s, row) for row in laps]


def main() -> int:
    import numpy as np
    from PIL import Image

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--every", type=float, default=4.0)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--roster", default=None,
                    help="where the cluster sheet and its labels live "
                         "(default: beside the capture)")
    ap.add_argument("--apply", action="store_true",
                    help="write the labelled names onto `traffic.rival`")
    ap.add_argument("--scratch", default=None)
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")
    scratch = Path(args.scratch) if args.scratch else Path.cwd() / "_board"
    scratch.mkdir(parents=True, exist_ok=True)
    roster_path = (Path(args.roster) if args.roster
                   else scratch / f"roster-session-{args.session}.json")

    marks = crossings(store, args.session, args.offset)
    end = marks[-1][0]
    print(f"reading the board every {args.every:g} s over 0-{end:.0f} s")

    seen: list = []
    # The native crop behind each reading, and the bits made from it, both
    # keyed by sighting - so a cluster can be shown to the operator at the
    # resolution the board was actually drawn at.
    raw_by_key: dict = {}
    bits_by_key: dict = {}
    at, shot = 0.0, scratch / "board.png"
    no_own = 0
    refused: collections.Counter = collections.Counter()
    while at <= end:
        if frame_at(video, at, shot):
            pixels = np.asarray(Image.open(shot).convert("RGB"))
            if tuple(pixels.shape[1::-1]) != CANVAS:
                raise SystemExit(f"capture is not {CANVAS[0]}x{CANVAS[1]}")
            found = read_frame(pixels, tally=refused)
            if found is None:
                no_own += 1
            else:
                for side, _y, bits, crop in found:
                    key = (round(at, 2), side)
                    seen.append((key, bits))
                    raw_by_key[key], bits_by_key[key] = crop, bits
        at += args.every

    groups = cluster(seen)
    print(f"  {len(seen)} name(s) read, {no_own} frame(s) where his own row "
          f"could not be told apart")
    # **The refusals, out loud.** CLAUDE.md 4.10: the number setting the bar
    # never appeared in the log, so a ratchet was invisible for a whole race.
    for reason, count in sorted(refused.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>5} strip(s) refused: {reason}")
    print()
    labels = {}
    if roster_path.exists():
        labels = json.loads(roster_path.read_text(encoding="utf-8"))

    out = {}
    for n, group in enumerate(groups):
        key = str(n)
        png = scratch / f"name-{args.session}-{n}.png"
        Image.fromarray((group["bits"] * 255).astype("uint8")).resize(
            (NAME_SHAPE[0] * 4, NAME_SHAPE[1] * 4), Image.NEAREST).save(png)
        # **The one the operator actually reads**, and picking its samples by
        # typicality alone was wrong in the direction that matters. Distance
        # from the cluster's running average measures how ALIKE a sighting is
        # to the rest - so where an occlusion sits in a majority of sightings
        # the exemplar absorbs it, and the three nearest are exactly the three
        # carrying it. That defeats the reason for showing three.
        #
        # Typicality still picks the shortlist, because a badly-cut crop is
        # worth excluding; the three shown are then spread across the race, so
        # a marshal's post standing in one is not standing in the next. Note
        # the ranking is done in the 64x16 space this file calls unreadable -
        # it is fit to say which crops resemble each other, which is all it is
        # asked, and not to say what any of them says.
        order = sorted(group["seen"],
                       key=lambda k: (bits_by_key[k] != group["bits"]).mean())
        shortlist = sorted(order[:RAW_SHORTLIST])      # ...back into time order
        if len(shortlist) <= RAW_SAMPLES:
            picked = shortlist
        else:
            step = (len(shortlist) - 1) / (RAW_SAMPLES - 1)
            picked = [shortlist[round(i * step)] for i in range(RAW_SAMPLES)]
        crops = [raw_by_key[k] for k in picked]
        raw_png = scratch / f"name-{args.session}-{n}-raw.png"
        _legible(crops, raw_png)
        name = labels.get(key, {}).get("name") if isinstance(
            labels.get(key), dict) else labels.get(key)
        # `read_this` first, and the exemplar named for what it is. The roster
        # is the file the operator opens, and a key called `bitmap` sitting
        # above it is an invitation to open the one thing that cannot be read.
        out[key] = {"name": name, "read_this": raw_png.name,
                    "sightings": len(group["seen"]),
                    "exemplar_do_not_read": png.name}
        print(f"  {n:>2}  {len(group['seen']):>3} sighting(s)  "
              f"{raw_png.name}  -> {name or '<unnamed>'}")

    roster_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nroster: {roster_path}")

    if not args.apply:
        print(f"Open each `-raw.png` - NOT the {NAME_SHAPE[0]}x{NAME_SHAPE[1]} "
              f"exemplar, which is for the clustering and cannot be read - "
              f"write the name into the roster, then re-run with --apply.")
        return 0

    unnamed = [k for k, v in out.items() if not v["name"]]
    if unnamed:
        raise SystemExit(
            f"cluster(s) {', '.join(unnamed)} have no name in the roster. A "
            f"contact named from an unlabelled cluster would be a guess, so "
            f"nothing is written. Where the `-raw.png` genuinely cannot be "
            f"read - two rows rendered over each other as the board "
            f"reorders - put "
            f'"{UNREADABLE}" and those contacts stay unnamed rather than '
            f"blocking the rest.")

    # Which name was beside him at each sample, by side.
    named: dict[tuple[float, str], str] = {}
    for n, group in enumerate(groups):
        name = out[str(n)]["name"]
        if name == UNREADABLE:
            continue
        for key in group["seen"]:
            named[key] = name

    rows = store.list_traffic(args.session)
    if not rows:
        raise SystemExit(f"session {args.session} has no `traffic` rows - run "
                         f"tools/read_replay_traffic.py --apply first")

    # **Nearest board reading on the same side, not the same timestamp.** The
    # radar is worth sampling faster than the board - a pass is over in
    # seconds and the running order is not - so the two runs do not land on
    # the same frames and an exact match named 59 contacts of 626.
    #
    # Bounded by the board's own interval: beyond that the order may have
    # changed in between, and a name carried across a pass would put the wrong
    # driver on the car. Contacts outside it stay unnamed.
    by_side: dict[str, list] = collections.defaultdict(list)
    for (when, side), name in named.items():
        by_side[side].append((when, name))
    for side in by_side:
        by_side[side].sort()

    written = 0
    for row in rows:
        candidates = by_side.get(row["side"] or "", [])
        best = None
        for when, name in candidates:
            gap = abs(when - row["video_s"])
            if best is None or gap < best[0]:
                best = (gap, name)
        if best is not None and best[0] <= args.every:
            store.name_traffic(row["id"], best[1])
            written += 1
    print(f"named {written} of {len(rows)} contact(s), matched within "
          f"{args.every:g} s of a board reading")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
