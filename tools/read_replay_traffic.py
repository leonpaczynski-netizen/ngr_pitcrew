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
# **LEGACY.** Where the radar sat on the captures this tool was written
# against. Those captures are gone - session 88 has no `video_path` and the
# file at session 112's path today is a PS5 share-viewer recording with no HUD
# on it at all - and the driver has since stopped racing in VR and records
# every practice and race on the layout below. Kept as the fallback seed and
# as the source of `RADAR_OFFSETS`; nothing should rely on it being right.
RADAR = (1620, 830, 1900, 1000)
OWN_XY = (1750, 907)
CANVAS = (1920, 1080)

# **The radar is not always there, and a fixed box is why this returned
# nothing on a whole league race.** Daytona session 143 read 0 contacts from
# 595 samples: that box is bare tarmac on its capture, and the radar sits
# centre-bottom between the dials. The widget is the same size in both - the
# marker's y is 907 either way - so only x moves, with the HUD layout.
#
# The own marker is found instead of assumed. Measured over frames of Sardegna
# 159 and Daytona 143, every red thing in the band below the screen centre:
#
#     the marker        6-15 x 5-14 px, area 26-76, centre y 907-910
#     the gear number   40 x 150, centre y 915
#     the rev counter   38 x 80,  centre y 951-959
#     the tyre RS pips  12-14 x 2-15, centre y 961-968
#     a flat bar        15 x 6 at y 902 - the one thing close in y, and it is
#                       twice as wide as tall where the marker never is
#
# So: a small, roughly upright red blob whose centre sits within a few pixels
# of 907. The bar is excluded by shape and everything else by size or by y.
# The marker's centre y measured 907-910 across both captures, n=9. The band
# is kept tight on purpose: at 918 the detector picked up the top edge of the
# REV COUNTER on a Daytona practice capture and reported the radar as being
# four hundred pixels away.
OWN_MARKER_BAND = (890, 926)
OWN_MARKER_Y = (902, 914)
OWN_MARKER_AREA = (20, 150)
OWN_MARKER_MAX_SIDE = 24
# Height over width. The marker measured 0.83 at its flattest; the bar at y
# 902 measured 0.40.
OWN_MARKER_MIN_ASPECT = 0.6
# The box around the marker, kept at the offsets the original geometry had:
# `RADAR` less `OWN_XY` is 130 left, 150 right, 77 up, 93 down.
RADAR_OFFSETS = (130, 77, 150, 93)

# **The marker is not reliably red, and the crosshair always is bright.** The
# HUD is translucent: over dark tarmac the red arrow separates cleanly, over
# the bright concrete at Daytona it washes out and the colour test finds
# nothing. Measured on the race capture, the arrow was found on 2 frames of
# 16.
#
# What does not vary is that the widget is STATIC and the track is not. A
# per-pixel median over a dozen frames keeps the HUD and averages the scenery
# into a flat grey, and on that image the radar's horizontal crosshair is a
# long bright run straight through the marker:
#
#     longest run 248 px at y=908, x 836-1083, centre x 960
#
# which is the marker's own position, found by a route that does not depend on
# what the car is driving over.
RADAR_SAMPLE_FRAMES = 12
CROSSHAIR_BAND = (860, 960)
CROSSHAIR_LUM = 60
CROSSHAIR_MIN_RUN = 120

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

# **The radar is a perspective projection, so there is no single metres per
# pixel - and this is the measurement that says so.**
#
# Fitted against his own path out of `lap_frames`, rotating it heading-up and
# scoring the overlay against the ribbon mask, on four frames of the Fuji
# race: points within 60 m of the car want 2.80, 3.35 and 3.95 m/px; points
# between 100 and 200 m want 7.95 or more, which is the top of the search
# range. The best-fit ROTATION differs between the two bands on the same
# frame too, which is the second signature of a transform that is not a
# similarity.
#
# So metres are reported inside the near field and refused outside it. That
# is where racing happens - a tow is tens of metres, not hundreds - and a
# figure at range would be one this tool invented. Rule 5.
NEAR_FIELD_PX = 20.0
NEAR_M_PER_PX = 3.4
# The spread of the three near-field fits, carried so the report can say what
# the number is worth rather than printing it to a precision it has not got.
NEAR_M_PER_PX_SPREAD = 0.6


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


def find_own_marker(pixels):
    """`(x, y)` of the driver's own marker on the radar, or None.

    Searched rather than assumed, because the widget moves with the HUD
    layout - see `OWN_MARKER_BAND`. Returns the blob nearest the measured y,
    so a frame carrying two candidates picks the one on the radar.
    """
    import numpy as np
    top, bottom = OWN_MARKER_BAND
    band = pixels[top:bottom].astype(int)
    r, g, b = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    red = (r > 110) & (r - g > 55) & (r - b > 55)
    best = None
    seen = np.zeros(red.shape, dtype=bool)
    height, width = red.shape
    for sy in range(height):
        for sx in range(width):
            if not red[sy, sx] or seen[sy, sx]:
                continue
            stack, cells = [(sy, sx)], []
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                cells.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if (0 <= ny < height and 0 <= nx < width
                            and red[ny, nx] and not seen[ny, nx]):
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if not OWN_MARKER_AREA[0] <= len(cells) <= OWN_MARKER_AREA[1]:
                continue
            ys = [c[0] for c in cells]
            xs = [c[1] for c in cells]
            w, h = max(xs) - min(xs) + 1, max(ys) - min(ys) + 1
            if w > OWN_MARKER_MAX_SIDE or h > OWN_MARKER_MAX_SIDE:
                continue
            if h / w < OWN_MARKER_MIN_ASPECT:
                continue                      # a flat bar is not the marker
            cy = sum(ys) / len(ys) + top
            if not OWN_MARKER_Y[0] <= cy <= OWN_MARKER_Y[1]:
                continue
            off = abs(cy - (OWN_MARKER_Y[0] + OWN_MARKER_Y[1]) / 2)
            if best is None or off < best[0]:
                best = (off, int(round(sum(xs) / len(xs))), int(round(cy)))
    return None if best is None else (best[1], best[2])


def radar_box(own):
    """The search box around a found marker, at the measured offsets."""
    left, up, right, down = RADAR_OFFSETS
    return (own[0] - left, own[1] - up, own[0] + right, own[1] + down)


def masks(pixels, box=RADAR):
    """Ribbon, own marker and rival arrows, as boolean arrays."""
    import numpy as np
    box = pixels[box[1]:box[3], box[0]:box[2]].astype(int)
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


def contacts(pixels, own_xy=OWN_XY) -> list[dict] | None:
    """Every rival arrow on the radar this frame, with side and ribbon distance.

    None where the ribbon could not be found at all - which is not the same as
    "nobody was there", and the caller says so rather than filing an empty lap.

    `own_xy` is where the driver's own marker sits on THIS capture; the box is
    taken around it. It used to be a constant, and the constant was wrong for
    a whole league race.
    """
    import numpy as np
    box = radar_box(own_xy)
    ribbon, own, rival = masks(pixels, box)
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
            out.append({"px": None, "side": None, "near_m": None,
                        "size": len(points)})
            continue
        nearest = min(on, key=lambda pair: pair[0])
        px = round(nearest[0], 1)
        out.append({"px": px,
                    "side": AHEAD if nearest[1] > 0 else BEHIND,
                    # Null beyond the near field, never extrapolated.
                    "near_m": (round(px * NEAR_M_PER_PX, 1)
                               if px <= NEAR_FIELD_PX else None),
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


def resolve_offset(store, session_id: int, given):
    """The video offset: what was typed, or what the app already wrote down.

    **`--offset` was the thing standing between "run this after every race"
    and "run it when somebody has ten minutes."** The app records the wall
    clock at video second zero when it starts the recording, and every lap
    carries the wall clock at its crossing, so the number is a subtraction -
    exact, rather than the few-seconds-early estimate this used to take.

    An explicit `--offset` still wins: a capture made by hand, or a replay
    recorded from partway through, has no stored zero and the operator is the
    only one who knows it.
    """
    if given is not None:
        return float(given), "given on the command line"
    from pitcrew.race.video_index import offset_for

    derived = offset_for(store, session_id)
    if derived is not None:
        return derived, "derived from the recording the app started"
    # **Zero, and SAID.** A capture made by hand has no stored zero, and zero
    # is the right assumption for a replay trimmed to the race - it is what
    # this defaulted to silently before any of it was derivable. What is new
    # is that it says so: a plausible default standing in for "nobody knows"
    # is this codebase's most repeated defect, and the fix is not to refuse,
    # it is to make the assumption audible.
    return 0.0, ("ASSUMED zero - the app did not start this recording, so "
                 "there is no stored video zero. Pass --offset if the "
                 "capture does not begin at the first crossing")


def locate_radar(video, start: float, end: float, shot, given):
    """Where the own marker sits on THIS capture, from the capture itself.

    Sampled at several points rather than one, and the answer has to agree:
    the widget does not move during a race, so two readings that disagree mean
    the detector has found something else and the number cannot be trusted.

    **Refuses rather than falling back.** The old constant belongs to a HUD
    layout that is not recorded any more, and using it when detection fails
    would put the box on bare tarmac and report an empty race - which is
    exactly what happened, silently, for a whole league round.
    """
    import numpy as np
    from PIL import Image

    if given is not None:
        return (given, OWN_XY[1])

    # **The crosshair on a median image**, which is the reading that holds.
    top, bottom = CROSSHAIR_BAND
    stack = []
    for index in range(RADAR_SAMPLE_FRAMES):
        at = start + (end - start) * (index + 1) / (RADAR_SAMPLE_FRAMES + 1)
        if not frame_at(video, at, shot):
            continue
        with Image.open(shot) as image:
            stack.append(np.asarray(image.convert("RGB"))[top:bottom])
    if len(stack) >= 4:
        lum = np.median(np.stack(stack), axis=0).mean(axis=2)
        best = (0, 0, 0)
        for row in range(lum.shape[0]):
            run, x0 = 0, 0
            for x, on in enumerate(lum[row] > CROSSHAIR_LUM):
                if not on:
                    run = 0
                    continue
                if run == 0:
                    x0 = x
                run += 1
                if run > best[0]:
                    best = (run, row, x0)
        length, row, x0 = best
        centre_y = row + top
        if (length >= CROSSHAIR_MIN_RUN
                and OWN_MARKER_Y[0] <= centre_y <= OWN_MARKER_Y[1]):
            return (x0 + length // 2, centre_y)

    # Falls back to the red arrow, which is what the crosshair reading was
    # measured against and which works wherever the HUD sits over dark tarmac.
    seen = []
    for share in [(index + 1) / 17 for index in range(16)]:
        at = start + (end - start) * share
        if not frame_at(video, at, shot):
            continue
        # **Closed before the next write.** `Image.open` holds the file until
        # it is collected, and on Windows ffmpeg cannot then overwrite it - so
        # every later grab failed silently and sixteen samples came back as
        # two. It looked like the marker being absent; it was the frame never
        # being replaced.
        with Image.open(shot) as image:
            found = find_own_marker(np.asarray(image.convert("RGB")))
        if found is not None:
            seen.append(found)
    if not seen:
        raise SystemExit(
            "could not find the radar's own marker on this capture. It is a "
            "small upright red blob at the centre of the radar; if this "
            "recording has no radar on screen there is nothing to read, and "
            "if it has one somewhere unexpected pass --radar-x with its x.")
    # **The agreeing majority, not unanimity.** One frame in eight catches a
    # brake light or a kerb through the panel and reports a marker somewhere
    # else; demanding every reading agree turns that into a refusal on a
    # capture that is perfectly readable. The widget does not move, so the
    # true x is the one most frames land on.
    best, votes = None, 0
    for x, _ in seen:
        agree = [v for v in seen if abs(v[0] - x) <= 3]
        if len(agree) > votes:
            best, votes = agree, len(agree)
    if votes < 3:
        raise SystemExit(
            f"the marker was found on only {votes} frame(s) of "
            f"{len(seen)} read, at x {sorted(x for x, _ in seen)} - too few "
            f"to trust. Pass --radar-x with the x of the red marker at the "
            f"centre of the radar.")
    if votes * 2 < len(seen):
        raise SystemExit(
            f"the marker was found in {len(seen)} frame(s) at x values "
            f"{sorted(x for x, _ in seen)} and no x holds a majority - it "
            f"does not move during a race, so something else is being "
            f"matched. Pass --radar-x with the x of the red marker at the "
            f"centre of the radar.")
    return (sorted(x for x, _ in best)[votes // 2],
            sorted(y for _, y in best)[votes // 2])


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
    ap.add_argument("--offset", type=float, default=None,
                    help="video seconds at the first crossing. **Derived when "
                         "the app started the recording** - it wrote down the "
                         "wall clock at video second zero, so the offset is a "
                         "subtraction rather than the few-seconds-early "
                         "estimate this used to take. Pass it only for a "
                         "capture made by hand, which has no stored zero")
    ap.add_argument("--apply", action="store_true",
                    help="write the contacts to `traffic`, replacing "
                         "whatever that session already had")
    ap.add_argument("--radar-x", type=int, default=None,
                    help="x of the driver's own marker on the radar. Found "
                         "from the capture itself; pass this only when it "
                         "cannot be, which the tool says rather than "
                         "falling back to a number from another layout")
    ap.add_argument("--scratch", default=None,
                    help="where to put the extracted frames")
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")
    scratch = Path(args.scratch) if args.scratch else Path.cwd() / "_traffic"
    scratch.mkdir(parents=True, exist_ok=True)

    offset, how = resolve_offset(store, args.session, args.offset)
    print(f"video offset {offset:.2f} s, {how}")
    marks = crossings(store, args.session, offset)
    start, end = 0.0, marks[-1][0]
    print(f"sampling {video.name} every {args.every:g} s over "
          f"{start:.0f}-{end:.0f} s")

    own_xy = locate_radar(video, start, end, scratch / "locate.png",
                          args.radar_x)
    print(f"radar own marker at {own_xy}, box {radar_box(own_xy)}")

    per_lap: dict[int, list] = collections.defaultdict(list)
    filed: list[dict] = []
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
                found = contacts(pixels, own_xy)
                samples += 1
                if found is None:
                    blind[row["lap_num"]] += 1
                else:
                    per_lap[row["lap_num"]].append(found)
                    for contact in found:
                        # The race-order neighbour: an inference, stored
                        # under a name that says so. It holds while nobody
                        # between them is a lap down.
                        neighbour = None
                        if contact["side"] == AHEAD and row["position"] > 1:
                            neighbour = row["position"] - 1
                        elif contact["side"] == BEHIND:
                            neighbour = row["position"] + 1
                        filed.append({
                            "lap_id": row["id"], "lap_num": row["lap_num"],
                            "video_s": round(at, 2), "side": contact["side"],
                            "ribbon_px": contact["px"],
                            "near_m": contact["near_m"],
                            "rival_position": neighbour,
                            "source": "replay-radar"})
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

    print("")
    print(f"ribbon pixels. Metres only inside {NEAR_FIELD_PX:.0f} px at "
          f"{NEAR_M_PER_PX:.1f} +/- {NEAR_M_PER_PX_SPREAD:.1f} m/px - the "
          f"radar is a perspective projection and the far field wants 8 or "
          f"more, so a metre figure at range would be invented.")
    print("`pos` and the position moves come from the packet and are already "
          "in the archive; they are the ground truth this is read against.")
    print("`blind` counts samples whose ribbon could not be found at all - "
          "not the same as nobody being there.")
    if args.apply:
        written = store.record_traffic(args.session, filed)
        print("")
        print(f"wrote {written} contact(s) to `traffic` as 'replay-radar'")
    else:
        print("")
        print(f"report only - {len(filed)} contact(s) would be written; "
              f"pass --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
