"""Run the PRODUCTION board readers over real frames of a race recording.

    python tools/board_bench.py --video "<capture.mp4>" --frames 73
    python tools/board_bench.py --video "<capture.mp4>" --frames 12 --verbose

**This exists because two implementations of one reading disagreed and only
the one nothing depends on worked.** `tools/read_replay_board.py` reads the
board off a capture reliably - 33 names over 37 frames, his own row on 36 - and
it carries its own `flag_rows` and `own_row` against fixed pixel windows. It
does not import `telemetry/board.py`, so its success said nothing at all about
the live pit wall. Fed 73 frames of the 4 Sep race, the production
`flag_ladder` found a board on 5, `read_gaps` on 0 and `pit_columns` on 0,
which is the wall's whole-race silence reproduced on the bench.

Every reader here is imported from the app. Nothing is reimplemented, because
a reimplementation is what hid the fault for a fortnight.

The repaired locator gives 119 ladders on a 120-frame sample of the same race,
119 of them on the board and 118 own rows anchored to a rung of their own
ladder, against 4 / 3 / 3 before.

### What the counts mean

* **ladder** - `board.flag_ladder` returned a column and rungs at all.
* **on the board** - and that column is where a leaderboard's flags are, at
  10-20% of the frame width. A ladder anywhere else is catch fencing, a
  grandstand or the track at the frame edge, all of which have beaten the
  board on rung count at some point.
* **anchored** - `board.own_row` landed on one of that ladder's own rungs
  rather than on a bright patch of sky somewhere else.
* **gap_boxes** - `board.gap_lines` framed the two gap readouts. Framing them
  is not reading them: at a 1080-row capture the glyphs are 12 px and
  `hud_digits` scores them 0.60-0.70 against its 0.80 floor, so **gaps_read is
  expected to be 0 until the digit bank is extended to this size** and a
  non-zero count there would be the surprise.
* **pit_rows** - `pit_columns.read_rows`, which is empty until somebody pits
  and is not a failure before that.

Frames are decoded one `-ss` seek at a time, the same way
`tools/read_replay_board.py` does it, and cached as PNGs so a second run is
free.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np                                               # noqa: E402
from PIL import Image                                            # noqa: E402

from pitcrew.race.gaps import read_gaps                          # noqa: E402
from pitcrew.telemetry.board import (                            # noqa: E402
    flag_ladder, gap_lines, own_row,
)
from pitcrew.telemetry.pit_columns import read_rows              # noqa: E402

# Where a leaderboard's flag column sits, as a fraction of frame width. Not a
# search bound - the readers use none - only how this bench decides whether the
# thing that was found is the board or the scenery.
BOARD_X_BAND = 0.10, 0.20
# How near a rung the driver's own row must land to count as anchored to it.
ANCHOR_TOL_PX = 8


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                            # noqa: BLE001
        return "ffmpeg"


def frame_at(video: Path, seconds: float, out: Path) -> bool:
    if out.exists():
        return True
    result = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1",
         "-y", str(out)], capture_output=True)
    return result.returncode == 0 and out.exists()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=float, default=30.0)
    ap.add_argument("--end", type=float, default=2200.0)
    ap.add_argument("--frames", type=int, default=45)
    ap.add_argument("--cache", default=None,
                    help="where decoded frames are kept (default: ./_bench)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")
    if args.frames < 2:
        raise SystemExit("--frames must be at least 2 to span an interval")
    cache = Path(args.cache) if args.cache else Path.cwd() / "_bench"
    cache.mkdir(parents=True, exist_ok=True)

    step = (args.end - args.start) / (args.frames - 1)
    seen = ladders = on_board = anchored = boxes = read = pits = 0
    for index in range(args.frames):
        at = args.start + index * step
        shot = cache / f"f{at:08.2f}.png"
        if not frame_at(video, at, shot):
            print(f"{at:7.1f}  could not decode")
            continue
        pixels = np.asarray(Image.open(shot).convert("RGB"))
        seen += 1
        ladder = flag_ladder(pixels)
        row = own_row(pixels, ladder)
        low, high = BOARD_X_BAND
        here = bool(ladder) and (low * pixels.shape[1] <= ladder[0]
                                 <= high * pixels.shape[1])
        on_rung = bool(row) and bool(ladder) and any(
            abs((row[1] + row[3]) // 2 - y) <= ANCHOR_TOL_PX for y in ladder[2])
        framed = gap_lines(pixels, row) if row else (None, None)
        gaps = read_gaps(pixels, row) if row else (None, None)
        rows = read_rows(pixels, row, ladder) if row else []
        ladders += ladder is not None
        on_board += here
        anchored += on_rung
        boxes += sum(box is not None for box in framed)
        read += sum(value is not None for value in gaps)
        pits += bool(rows)
        if args.verbose:
            where = (f"x{ladder[0]}-{ladder[1]} n={len(ladder[2])}"
                     if ladder else "-")
            print(f"{at:7.1f}  ladder {where:>22}{'' if here else '  (NOT THE '
                  'BOARD)'}  own {str(row):>28}  gaps {gaps}  "
                  f"boxes {sum(b is not None for b in framed)}  "
                  f"pit rows {len(rows)}")

    print(f"\n{seen} frame(s) of {video.name}, "
          f"{args.start:.0f}-{args.end:.0f} s"
          f"\n  ladder          {ladders:>4}"
          f"\n  on the board    {on_board:>4}"
          f"\n  own row         {anchored:>4}  (anchored to one of its rungs)"
          f"\n  gap boxes       {boxes:>4}  of {2 * seen}"
          f"\n  gaps read       {read:>4}  of {2 * seen}"
          f"\n  frames with pit columns {pits:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
