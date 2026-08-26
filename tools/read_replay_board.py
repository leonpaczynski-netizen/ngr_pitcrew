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

### Finding the rows, on a panel you can see through

The leaderboard is translucent and the scenery behind it moves, so thresholding
for rows finds sky as often as it finds a row - measured, on 3 frames of 7.
Two anchors survive that:

* **the flags.** One per driver row, at a fixed x, a saturated blue nothing
  behind the panel reproduces. They give the row grid at a 40 px pitch, and
  the 67-72 px steps are where a gap row sits - a row that carries a time and
  no flag.
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
# Half-height of the strip a name is read from, about the flag's centre.
NAME_HALF_H = 12
# Fewer ink pixels than this is not a name.
NAME_MIN_INK = 40
# Every name is normalised to this before being compared, so a crop a pixel
# wider does not read as a different driver.
NAME_SHAPE = (64, 16)
# **Two bitmaps closer than this are the same name.** Measured on the Fuji
# race: at 0.12 the same driver split into two clusters, so it is set wider
# and the operator sees the merge rather than the split - a split invents a
# driver, a merge is visible the moment the sheet is looked at.
SAME_NAME_MAX_DIFF = 0.18
# **What to write against a cluster nobody can read.** The board reorders
# between frames and a sample caught mid-reorder has two names rendered over
# each other. Marking it explicitly leaves those contacts unnamed and lets the
# rest through; leaving it blank blocks everything, and guessing at it puts a
# driver's name on a car that was never there.
UNREADABLE = "-"


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


def own_row(pixels, rows: list[int]) -> int | None:
    """Which of those rows is his. **The white background, not the position.**"""
    if not rows:
        return None
    brightness = [pixels[y - 13:y + 13, NAME_X[0]:NAME_X[1]].mean()
                  for y in rows]
    best = max(range(len(rows)), key=lambda i: brightness[i])
    # A row that is not clearly brighter than the rest is not his: the panel
    # is translucent and a white wall behind it can lift any row.
    others = sorted(brightness)[:-1]
    if others and brightness[best] - max(others) < 20:
        return None
    return best


def name_bitmap(pixels, y: int, own: bool):
    """One row's name, cropped to its ink and normalised."""
    from PIL import Image
    import numpy as np
    strip = pixels[y - NAME_HALF_H:y + NAME_HALF_H,
                   NAME_X[0]:NAME_X[1]].astype(int)
    if strip.size == 0:
        return None
    lum = strip.mean(axis=2)
    # Dark glyphs on his white row, bright glyphs on everyone else's.
    ink = lum < 120 if own else lum > 185
    ys, xs = np.where(ink)
    if len(xs) < NAME_MIN_INK:
        return None
    crop = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    scaled = Image.fromarray((crop * 255).astype("uint8")).resize(NAME_SHAPE)
    return np.asarray(scaled) > 127


def cluster(bitmaps: list) -> list[dict]:
    """Group identical names. Exact, because the font never changes."""
    groups: list[dict] = []
    for key, bits in bitmaps:
        for group in groups:
            if (group["bits"] != bits).mean() < SAME_NAME_MAX_DIFF:
                group["seen"].append(key)
                break
        else:
            groups.append({"bits": bits, "seen": [key]})
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
    at, shot = 0.0, scratch / "board.png"
    no_own = 0
    while at <= end:
        if frame_at(video, at, shot):
            pixels = np.asarray(Image.open(shot).convert("RGB"))
            if tuple(pixels.shape[1::-1]) != CANVAS:
                raise SystemExit(f"capture is not {CANVAS[0]}x{CANVAS[1]}")
            rows = flag_rows(pixels)
            index = own_row(pixels, rows)
            if index is None:
                no_own += 1
            else:
                for offset, side in ((-1, "ahead"), (1, "behind")):
                    j = index + offset
                    if 0 <= j < len(rows):
                        bits = name_bitmap(pixels, rows[j], own=False)
                        if bits is not None:
                            seen.append(((round(at, 2), side), bits))
        at += args.every

    groups = cluster(seen)
    print(f"  {len(seen)} name(s) read, {no_own} frame(s) where his own row "
          f"could not be told apart\n")
    labels = {}
    if roster_path.exists():
        labels = json.loads(roster_path.read_text(encoding="utf-8"))

    out = {}
    for n, group in enumerate(groups):
        key = str(n)
        png = scratch / f"name-{args.session}-{n}.png"
        Image.fromarray((group["bits"] * 255).astype("uint8")).resize(
            (NAME_SHAPE[0] * 4, NAME_SHAPE[1] * 4), Image.NEAREST).save(png)
        name = labels.get(key, {}).get("name") if isinstance(
            labels.get(key), dict) else labels.get(key)
        out[key] = {"name": name, "sightings": len(group["seen"]),
                    "bitmap": png.name}
        print(f"  {n:>2}  {len(group['seen']):>3} sighting(s)  "
              f"{png.name}  -> {name or '<unnamed>'}")

    roster_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nroster: {roster_path}")

    if not args.apply:
        print("Open each bitmap, write the name into the roster, then re-run "
              "with --apply.")
        return 0

    unnamed = [k for k, v in out.items() if not v["name"]]
    if unnamed:
        raise SystemExit(
            f"cluster(s) {', '.join(unnamed)} have no name in the roster. A "
            f"contact named from an unlabelled cluster would be a guess, so "
            f"nothing is written. Where a bitmap genuinely cannot be read - "
            f"two rows rendered over each other as the board reorders - put "
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
