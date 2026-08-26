"""Who was around him, read off the replay's proximity radar.

    python tools/read_replay_traffic.py --session 88 --video "<path>" \
        --every 5 --offset 8.10

**The feed carries a car COUNT and nothing else.** `cars_in_race` and one
field the parser marks "possible race position" are the entirety of what the
app knows about anyone else on track, so every race it has ever reasoned about
was reasoned about as though the driver were alone. Time lost in traffic, a
lap spent behind someone before the pass, whether an overcut worked against a
real car - none of it exists in the archive and none of it can be recovered
from the stream.

The bottom-right widget is not decoration. It is a **car-relative proximity
radar**: the driver's own marker pinned at the crosshair, the track ahead and
behind drawn as a ribbon that rotates with his heading, and rivals as arrows
on it. That is the tow/slipstream channel `CLAUDE.md` §5.3 names as the
highest-value live call the app could make and says the feed cannot give.

**And it is the only race-craft instrument that survives a replay.** The
leaderboard's gap-ahead and gap-behind rows never populate in a replay and are
never visible in VR - the driver's own words, 26 Aug 2026 - so nothing else on
that screen carries who was near him.

### What this reports, and what it deliberately does not

**Presence and side, in ribbon pixels. Not metres.** The ribbon narrows toward
its ends, which is consistent with a perspective projection, and until that is
calibrated against his own path a metre figure would be a number this tool
invented. `CLAUDE.md` rule 5: nothing derived is presented as measured, and a
distance in metres is exactly the kind of figure a race engineer would act on.
Pixels are honest and they still answer the question that matters - was
somebody there, on which side, and for how long.

### Why the sign is trustworthy even though the distance is not

The radar is drawn heading-up, so the ribbon leaves the crosshair in two
branches and the one going up the screen is the road ahead. The flood fill
below labels every reachable pixel with the branch it was reached through, so
a rival's side is decided by the path taken to it rather than by where it
happens to sit on a curve - which is the whole difficulty, because in a
hairpin a car ahead can be drawn below the crosshair.

### Validation

Position changes are the ground truth and they are already in the archive:
`laps.position` comes from the packet. A contact that moves from ahead to
behind should land on a lap where the position column steps. The report prints
both side by side so the two can be read against each other rather than the
radar being believed on its own.

Fuji, session 88, at 4 s: laps 1-5 crowded on both sides while he takes three
places on lap 2; **zero contacts in 135 samples across laps 6-10**, the stint
after his stop, in clear air and last; laps 11-14 a contact ahead at 68 px
closing to 84, 102, 135 while he takes four places, and on the lap he takes
P5 the closest contact is **7 px BEHIND** - the pass itself; then 21, 23 and
20 samples of that car sitting on him through laps 16-18 before he breaks away
to 86 and 125 px over the last two. Every step of that agrees with the
position column, and none of it was in the archive.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store                              # noqa: E402

# The widget, at 1920x1080. Measured, not guessed: the driver's own marker
# sits at (1750.3, 907.0) with a standard deviation of 0.23 px across 36
# frames spread over a whole race, so the geometry is fixed and the own car
# needs no detection at all - it is a constant.
RADAR = (1620, 830, 1900, 1000)
OWN_XY = (1750, 907)
CANVAS = (1920, 1080)

# The ribbon is the bright tail of the box's luminance: the road behind it
# sits at a median of 50 and the 99th percentile is 203. Grey rather than
# coloured, which is what separates it from the two arrows.
RIBBON_LUM = 150
RIBBON_MAX_TINT = 40

# An arrow is a saturated blue against dark tarmac - a far better separation
# than the same arrows get on the top-right track map, where they are drawn
# over sky and a colour threshold fails on 89% of frames.
RIVAL_MIN_B_OVER_R = 45
RIVAL_MIN_B = 110
RIVAL_MIN_G_OVER_R = 15
# Smaller than this is a compression artefact rather than a car.
RIVAL_MIN_PX = 12

AHEAD, BEHIND = "ahead", "behind"


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                            # noqa: BLE001
        return "ffmpeg"


def frame_at(video: Path, seconds: float, out: Path) -> bool:
    """One frame, seeking before `-i` so a 34-minute AV1 capture stays cheap."""
    result = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.3f}", "-i", str(video),
         "-frames:v", "1", "-y", str(out)],
        capture_output=True)
    return result.returncode == 0 and out.exists()


def masks(pixels):
    """Ribbon, own marker and rival arrows, as boolean arrays."""
    import numpy as np
    box = pixels[RADAR[1]:RADAR[3], RADAR[0]:RADAR[2]].astype(int)
    r, g, b = box[:, :, 0], box[:, :, 1], box[:, :, 2]
    lum = (r + g + b) / 3
    ribbon = (lum > RIBBON_LUM) & (np.abs(r - b) < RIBBON_MAX_TINT)
    own = (r - g > 55) & (r - b > 45) & (r > 110)
    rival = ((b - r > RIVAL_MIN_B_OVER_R) & (b > RIVAL_MIN_B)
             & (g - r > RIVAL_MIN_G_OVER_R))
    return ribbon, own, rival


def branches(passable, seed):
    """Geodesic distance from the crosshair, and which branch reached each pixel.

    Returns `(distance, label)` where label is +1 for the road ahead, -1 for
    the road behind and 0 for the seed itself.

    **The branch is decided at the seed and carried outward**, not inferred
    from where a pixel ends up. On a hairpin the road ahead is drawn below the
    crosshair, so any rule reading the sign off a rival's own coordinates gets
    it backwards exactly where traffic matters most.
    """
    import numpy as np
    height, width = passable.shape
    distance = np.full((height, width), -1.0)
    label = np.zeros((height, width), dtype=int)
    sy, sx = seed
    distance[sy, sx] = 0.0
    queue = collections.deque([(sy, sx)])
    steps = ((1, 0), (-1, 0), (0, 1), (0, -1),
             (1, 1), (1, -1), (-1, 1), (-1, -1))
    while queue:
        y, x = queue.popleft()
        for dy, dx in steps:
            ny, nx = y + dy, x + dx
            if not (0 <= ny < height and 0 <= nx < width):
                continue
            if not passable[ny, nx] or distance[ny, nx] >= 0:
                continue
            distance[ny, nx] = distance[y, x] + (1.4142 if dy and dx else 1.0)
            # The seed's own neighbours found the branch; everything after
            # inherits it. Up the screen is the road ahead.
            label[ny, nx] = label[y, x] or (1 if dy < 0 else -1)
            queue.append((ny, nx))
    return distance, label


def blobs(mask, min_px: int):
    import numpy as np
    seen = mask.copy()
    height, width = seen.shape
    found = []
    for y in range(height):
        for x in range(width):
            if not seen[y, x]:
                continue
            queue = collections.deque([(y, x)])
            seen[y, x] = False
            points = []
            while queue:
                cy, cx = queue.popleft()
                points.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if (0 <= ny < height and 0 <= nx < width
                                and seen[ny, nx]):
                            seen[ny, nx] = False
                            queue.append((ny, nx))
            if len(points) >= min_px:
                found.append(points)
    return found


def contacts(pixels) -> list[dict] | None:
    """Every rival arrow on the radar this frame, with side and ribbon distance.

    None where the ribbon could not be found at all - which is not the same as
    "nobody was there", and the caller says so rather than filing an empty lap.
    """
    import numpy as np
    ribbon, own, rival = masks(pixels)
    if ribbon.sum() < 60:
        return None
    passable = ribbon | own
    grown = passable.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(passable, dy, 0), dx, 1)
    seed = (OWN_XY[1] - RADAR[1], OWN_XY[0] - RADAR[0])
    if not grown[seed]:
        return None
    distance, label = branches(grown, seed)

    out = []
    for points in blobs(rival, RIVAL_MIN_PX):
        on = [(distance[y, x], label[y, x]) for y, x in points
              if distance[y, x] >= 0]
        if not on:
            # An arrow the flood fill could not reach is one whose ribbon is
            # broken between here and the crosshair. Reported as unplaced
            # rather than dropped: it is a car, and pretending otherwise is
            # how "no traffic" comes to mean "the mask failed".
            out.append({"px": None, "side": None, "size": len(points)})
            continue
        nearest = min(on, key=lambda pair: pair[0])
        out.append({"px": round(nearest[0], 1),
                    "side": AHEAD if nearest[1] > 0 else BEHIND,
                    "size": len(points)})
    return out


def crossings(store: Store, session_id: int, offset_s: float):
    """Video seconds at each lap's crossing, from the wall clock on each row."""
    laps = store.list_laps(session_id)
    if not laps:
        raise SystemExit(f"session {session_id} has no laps")
    first = dt.datetime.fromisoformat(laps[0]["recorded_at"])
    start = first - dt.timedelta(milliseconds=laps[0]["lap_time_ms"])
    return [((dt.datetime.fromisoformat(row["recorded_at"]) - start
              ).total_seconds() + offset_s, row) for row in laps]


def lap_at(marks, seconds: float):
    for at, row in marks:
        if seconds <= at:
            return row
    return None


def main() -> int:
    import numpy as np
    from PIL import Image

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--every", type=float, default=4.0,
                    help="seconds between samples (default 4). Traffic moves "
                         "faster than tyre wear does, and a pass is over in a "
                         "few seconds: at 10 s the Fuji race showed laps 12-14 "
                         "taking places against nothing but distant contacts, "
                         "and at 4 s the same laps show the car being caught, "
                         "passed, and then sitting 7 px behind")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="video seconds at the green flag")
    ap.add_argument("--scratch", default=None,
                    help="where to put the extracted frames")
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")
    scratch = Path(args.scratch) if args.scratch else Path.cwd() / "_traffic"
    scratch.mkdir(parents=True, exist_ok=True)

    marks = crossings(store, args.session, args.offset)
    start, end = 0.0, marks[-1][0]
    print(f"sampling {video.name} every {args.every:g} s over "
          f"{start:.0f}-{end:.0f} s")

    per_lap: dict[int, list] = collections.defaultdict(list)
    blind = collections.Counter()
    samples = 0
    at = start
    shot = scratch / "frame.png"
    while at <= end:
        if frame_at(video, at, shot):
            pixels = np.asarray(Image.open(shot).convert("RGB"))
            if tuple(pixels.shape[1::-1]) != CANVAS:
                raise SystemExit(
                    f"capture is {pixels.shape[1]}x{pixels.shape[0]}; the "
                    f"radar geometry is measured at {CANVAS[0]}x{CANVAS[1]} "
                    f"and does not scale")
            row = lap_at(marks, at)
            if row is not None:
                found = contacts(pixels)
                samples += 1
                if found is None:
                    blind[row["lap_num"]] += 1
                else:
                    per_lap[row["lap_num"]].append(found)
        at += args.every

    print(f"  {samples} sample(s) read\n")
    print(f"{'lap':>4} {'pos':>4} {'samples':>8} {'ahead':>6} {'behind':>7} "
          f"{'closest ahead':>14} {'closest behind':>15}  blind")
    previous = None
    for _, row in marks:
        lap = row["lap_num"]
        seen = per_lap.get(lap, [])
        flat = [c for frame in seen for c in frame]
        ahead = [c["px"] for c in flat if c["side"] == AHEAD and c["px"]]
        behind = [c["px"] for c in flat if c["side"] == BEHIND and c["px"]]
        frames_ahead = sum(1 for f in seen if any(c["side"] == AHEAD for c in f))
        frames_behind = sum(1 for f in seen
                            if any(c["side"] == BEHIND for c in f))
        move = ""
        if previous is not None and row["position"] != previous:
            gained = previous - row["position"]
            move = f"  <== {'gained' if gained > 0 else 'lost'} {abs(gained)}"
        previous = row["position"]
        print(f"{lap:>4} {row['position']:>4} {len(seen):>8} "
              f"{frames_ahead:>6} {frames_behind:>7} "
              f"{(f'{min(ahead):.0f} px' if ahead else '-'):>14} "
              f"{(f'{min(behind):.0f} px' if behind else '-'):>15}  "
              f"{blind.get(lap, 0):>5}{move}")

    print("\nribbon pixels, NOT metres - the ribbon narrows toward its ends "
          "and that scale is not calibrated yet.")
    print("`pos` and the position moves come from the packet and are already "
          "in the archive; they are the ground truth this is read against.")
    print("`blind` counts samples whose ribbon could not be found at all - "
          "not the same as nobody being there.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
